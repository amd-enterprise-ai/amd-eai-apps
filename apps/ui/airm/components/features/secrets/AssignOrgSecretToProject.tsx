// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  SelectItem,
  Divider,
  DrawerForm,
  FormFieldComponent,
  FormSelect,
  NoDataDisplay,
  Status,
  StatusProps,
  StatusError,
} from '@amdenterpriseai/components';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useMemo } from 'react';

import { useTranslation } from 'next-i18next';

import { useSystemToast } from '@amdenterpriseai/hooks';

import { assignSecretToProject, fetchSecrets } from '@/services/app';

import { APIRequestError } from '@amdenterpriseai/utils/app';

import { FormField } from '@amdenterpriseai/types';
import { Project } from '@/types/projects';
import {
  AssignOrgSecretToProjectFormData,
  SecretsResponse,
} from '@/types/secrets';

import { z } from 'zod';
import { SecretScope } from '@/types/enums/secrets';
import { Secret } from '@/types/secrets';
import { SecretUseCase } from '@amdenterpriseai/types';
import { displayTimestamp } from '@amdenterpriseai/utils/app';
import { SecretProjectAssignedTo } from './SecretProjectAssignedTo';
import { getSecretStatusVariants } from '@/utils/secrets-status-variants';

interface Props {
  isOpen: boolean;
  project: Project;
  onClose: () => void;
}

export const AssignOrgSecretToProject: React.FC<Props> = ({
  isOpen,
  project,
  onClose,
}) => {
  const { t } = useTranslation('secrets');
  const { toast } = useSystemToast();
  const queryClient = useQueryClient();

  const { data: secretsData } = useQuery<SecretsResponse>({
    queryKey: ['secrets'],
    queryFn: fetchSecrets,
  });

  const selectableSecrets = useMemo(
    () =>
      (secretsData?.data ?? [])
        .filter(
          (secret) =>
            secret.scope === SecretScope.ORGANIZATION &&
            !secret.projectSecrets?.some((ps) => ps.project.id === project.id),
        )
        .sort((a, b) => a.name.localeCompare(b.name)),
    [secretsData?.data, project.id],
  );

  const { mutate: updateAssignment, isPending } = useMutation({
    mutationFn: async (data: AssignOrgSecretToProjectFormData) => {
      return assignSecretToProject(project.id, data.secretId);
    },
    onSuccess: () => {
      toast.success(t('form.assignOrgSecret.notification.success'));
      queryClient.invalidateQueries({
        queryKey: ['secrets', project?.id],
      });
      onClose();
    },
    onError: (error) => {
      toast.error(
        t('form.assignOrgSecret.notification.error'),
        error as APIRequestError,
      );
    },
  });

  const formSchema = useMemo(
    () =>
      z.object({
        secretId: z.string().min(1, {
          message: t('form.assignOrgSecret.field.secretId.error.required'),
        }),
      }) as z.ZodType<AssignOrgSecretToProjectFormData>,
    [t],
  );

  const handleFormSubmit = useCallback(
    async (data: AssignOrgSecretToProjectFormData): Promise<void> => {
      updateAssignment(data);
    },
    [updateAssignment],
  );

  const formContent: FormField<AssignOrgSecretToProjectFormData>[] = [
    {
      name: 'secretId',
      label: t('form.assignOrgSecret.field.secretId.label'),
      placeholder: t('form.assignOrgSecret.field.secretId.placeholder'),
      isRequired: false,
      component: (formElemProps) => (
        <FormSelect {...formElemProps}>
          {selectableSecrets.map((secret: Secret) => {
            return <SelectItem key={secret.id}>{secret.name}</SelectItem>;
          })}
        </FormSelect>
      ),
    },
  ];

  return (
    <DrawerForm<AssignOrgSecretToProjectFormData>
      isOpen={isOpen}
      isActioning={isPending}
      onFormSuccess={(values) => {
        handleFormSubmit({
          secretId: values.secretId,
        });
      }}
      onCancel={onClose}
      title={t('form.assignOrgSecret.title')}
      confirmText={t('form.assignOrgSecret.action.save')}
      cancelText={t('form.assignOrgSecret.action.cancel')}
      renderFields={(form) => {
        const watchSecretId = form.watch('secretId');
        const selectedSecret = selectableSecrets.find(
          (secret) => secret.id === watchSecretId,
        );

        return (
          <div>
            <div className="flex flex-col gap-4">
              {formContent.map((field) => (
                <FormFieldComponent<AssignOrgSecretToProjectFormData>
                  key={field.name}
                  formField={field}
                  errorMessage={form.formState.errors[field.name]?.message}
                  register={form.register}
                  form={form}
                />
              ))}
            </div>
            <Divider className="my-4" />
            <div className="flex flex-col gap-4">
              <h2>{t('form.assignOrgSecret.secretDetails.title')}</h2>
              <div className="flex flex-col gap-2">
                <span className="text-sm font-thin">
                  {t('form.assignOrgSecret.secretDetails.type.label')}
                </span>
                <span>{selectedSecret?.name ?? <NoDataDisplay />}</span>
              </div>
              <div className="flex flex-col gap-2">
                <span className="text-sm font-thin">
                  {t('form.assignOrgSecret.secretDetails.useCase.label')}
                </span>
                <span>
                  {selectedSecret ? (
                    selectedSecret.useCase ? (
                      t(`useCase.${selectedSecret.useCase}`)
                    ) : (
                      t(`useCase.${SecretUseCase.GENERIC}`)
                    )
                  ) : (
                    <NoDataDisplay />
                  )}
                </span>
              </div>

              <div className="flex flex-col gap-2">
                <span className="text-sm font-thin">
                  {t('form.assignOrgSecret.secretDetails.updatedAt.label')}
                </span>
                <span>
                  {selectedSecret?.updatedAt ? (
                    displayTimestamp(new Date(selectedSecret.updatedAt))
                  ) : (
                    <NoDataDisplay />
                  )}
                </span>
              </div>
              <div className="flex flex-col gap-2">
                <span className="text-sm font-thin">
                  {t('form.assignOrgSecret.secretDetails.assignedTo.label')}
                </span>
                <span>
                  {selectedSecret ? (
                    <SecretProjectAssignedTo secret={selectedSecret} />
                  ) : (
                    <NoDataDisplay />
                  )}
                </span>
              </div>
              <div className="flex flex-col gap-2">
                <span className="text-sm font-thin">
                  {t('form.assignOrgSecret.secretDetails.status.label')}
                </span>
                {selectedSecret?.status ? (
                  <Status
                    {...(getSecretStatusVariants(t)[
                      selectedSecret.status
                    ] as StatusProps)}
                    helpContent={
                      selectedSecret.statusReason ? (
                        <StatusError
                          statusReason={selectedSecret.statusReason}
                          secondaryStatusReasons={undefined}
                        />
                      ) : undefined
                    }
                    isClickable
                  />
                ) : (
                  <NoDataDisplay />
                )}
              </div>
            </div>
          </div>
        );
      }}
      validationSchema={formSchema}
    />
  );
};

export default AssignOrgSecretToProject;
