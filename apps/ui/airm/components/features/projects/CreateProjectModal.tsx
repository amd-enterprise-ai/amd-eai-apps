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
import type { DefaultValues } from 'react-hook-form';

import { useTranslation } from 'next-i18next';
import router from 'next/router';

import { useSystemToast } from '@amdenterpriseai/hooks';

import { createProject } from '@/services/app';

import { APIRequestError } from '@amdenterpriseai/utils/app';
import { gigabytesToBytes } from '@amdenterpriseai/utils/app';
import { getProjectEditUrl } from '@/utils/projects';

import { Cluster } from '@/types/clusters';
import { GpuPreemptionPolicy } from '@/types/enums/gpu-preemption-policy';
import {
  ProjectFormFields,
  ProjectGpuPreemptionFormFields,
} from '@/types/enums/project-form-fields';
import {
  CreateProjectFormData,
  CreateProjectRequest,
  ProjectWithResourceAllocation,
} from '@/types/projects';
import { UpdateQuotaRequest } from '@/types/quotas';

import { CREATE_PROJECT_GPU_PREEMPTION_DEFAULTS } from '@/components/features/projects/constants';
import {
  gpuPreemptionConfigFromFormData,
  refineGpuPreemptionFormData,
} from '@/components/features/projects/gpu-preemption-form';
import { ProjectWorkloadPreemption } from '@/components/features/projects/ProjectWorkloadPreemption';

import { ZodType, z } from 'zod';

interface Props {
  clusters: Cluster[];
  isOpen: boolean;
  onProjectCreate: (projectId: string) => void;
  onOpenChange: () => void;
  projects: ProjectWithResourceAllocation[];
}

const CreateProjectModal: React.FC<Props> = ({
  clusters,
  isOpen,
  onOpenChange,
  onProjectCreate,
  projects,
}) => {
  const i18nKeySet = 'projects';
  const { t } = useTranslation(i18nKeySet);
  const { toast } = useSystemToast();

  const onboardedClusters = useMemo(
    () => clusters.filter((c) => c.status !== 'verifying'),
    [clusters],
  );

  const queryClient = useQueryClient();
  const MAX_PROJECTS_IN_CLUSTER = 999;

  const defaultValues = useMemo(
    (): DefaultValues<CreateProjectFormData> => ({
      [ProjectFormFields.NAME]: '',
      [ProjectFormFields.DESCRIPTION]: '',
      [ProjectFormFields.CLUSTER_ID]: '',
      [ProjectGpuPreemptionFormFields.ENABLED]: false,
      [ProjectGpuPreemptionFormFields.POLICY]:
        CREATE_PROJECT_GPU_PREEMPTION_DEFAULTS.policy,
      [ProjectGpuPreemptionFormFields.THRESHOLD]:
        CREATE_PROJECT_GPU_PREEMPTION_DEFAULTS.threshold,
      [ProjectGpuPreemptionFormFields.GRACE_PERIOD]:
        CREATE_PROJECT_GPU_PREEMPTION_DEFAULTS.gracePeriod,
    }),
    [],
  );

  const ProjectSchema: ZodType<CreateProjectFormData> = useMemo(
    () =>
      z
        .object({
          [ProjectFormFields.NAME]: z
            .string()
            .trim()
            .min(2, t('modal.create.form.name.validation.length') || '')
            .max(41, t('modal.create.form.name.validation.length') || '')
            .regex(
              /^[a-z0-9]+(-[a-z0-9]+)*$/,
              t('modal.create.form.name.validation.format') || '',
            )
            .refine(
              (name) =>
                !projects.some(
                  (g) => g.name.toLowerCase() === name.toLowerCase(),
                ),
              {
                message: t('modal.create.form.name.validation.unique') || '',
              },
            ),
          [ProjectFormFields.DESCRIPTION]: z
            .string()
            .trim()
            .min(2, t('modal.create.form.description.validation.length') || '')
            .max(
              1024,
              t('modal.create.form.description.validation.length') || '',
            ),
          [ProjectFormFields.CLUSTER_ID]: z
            .string({
              required_error:
                t('modal.create.form.cluster.validation.required') || '',
            })
            .trim()
            .min(1, t('modal.create.form.cluster.validation.required') || '')
            .refine(
              (clusterId) => {
                const count = projects.filter(
                  (p) => p.clusterId === clusterId,
                ).length;
                return count < MAX_PROJECTS_IN_CLUSTER;
              },
              {
                message:
                  t(
                    'modal.create.form.cluster.validation.exceedProjectsCount',
                    {
                      num: MAX_PROJECTS_IN_CLUSTER,
                    },
                  ) || '',
              },
            ),
          [ProjectGpuPreemptionFormFields.ENABLED]: z.boolean(),
          [ProjectGpuPreemptionFormFields.POLICY]: z
            .nativeEnum(GpuPreemptionPolicy)
            .optional(),
          [ProjectGpuPreemptionFormFields.THRESHOLD]: z.number().optional(),
          [ProjectGpuPreemptionFormFields.GRACE_PERIOD]: z.number().optional(),
        })
        .superRefine((data, ctx) => {
          refineGpuPreemptionFormData(data, ctx, t);
        }),
    [t, projects],
  );

  const { mutate: createProjectMutation, isPending } = useMutation<
    ProjectWithResourceAllocation,
    Error,
    CreateProjectRequest
  >({
    mutationFn: createProject,
    onSuccess: (newProject) => {
      queryClient.invalidateQueries({ queryKey: ['projects'] });
      queryClient.invalidateQueries({ queryKey: ['quotas'] });
      toast.success(t('modal.create.notification.success'));

      onProjectCreate(newProject.id);
      router.push(getProjectEditUrl(newProject.id));
    },
    onError: (error) => {
      toast.error(
        t('modal.create.notification.error'),
        error as APIRequestError,
      );
      console.error('Error saving project:', error);
    },
  });

  const handleFormSuccess = useCallback(
    (data: CreateProjectFormData) => {
      const description = (
        data[ProjectFormFields.DESCRIPTION] as string
      ).trim();
      const name = (data[ProjectFormFields.NAME] as string).trim();
      const clusterId = data[ProjectFormFields.CLUSTER_ID] as string;

      const quota: UpdateQuotaRequest = {
        cpuMilliCores: 0,
        memoryBytes: gigabytesToBytes(0),
        ephemeralStorageBytes: gigabytesToBytes(0),
        gpuCount: 0,
      };

      const gpuPreemption = gpuPreemptionConfigFromFormData(data);

      createProjectMutation({
        name,
        description,
        clusterId,
        quota,
        gpuPreemption,
      });
    },
    [createProjectMutation],
  );

  return (
    <DrawerForm<CreateProjectFormData>
      isOpen={isOpen}
      isActioning={isPending}
      title={t('modal.create.title')}
      onOpenChange={onOpenChange}
      onFormSuccess={handleFormSuccess}
      onCancel={onOpenChange}
      validationSchema={ProjectSchema}
      defaultValues={defaultValues}
      cancelText={t('modal.create.actions.cancel')}
      confirmText={t('modal.create.actions.confirm')}
      renderFields={(form) => {
        return (
          <div className="flex flex-col gap-4">
            <FormFieldComponent<CreateProjectFormData>
              formField={{
                name: ProjectFormFields.NAME,
                label: t('modal.create.form.name.label'),
                placeholder: t('modal.create.form.name.placeholder'),
                description: t('modal.create.form.name.description'),
                isRequired: true,
                props: {
                  maxLength: 41,
                },
              }}
              errorMessage={
                form.formState.errors[ProjectFormFields.NAME]?.message
              }
              register={form.register}
            />
            <FormFieldComponent<CreateProjectFormData>
              formField={{
                name: ProjectFormFields.DESCRIPTION,
                label: t('modal.create.form.description.label'),
                isRequired: true,
                placeholder: t('modal.create.form.description.placeholder'),
                props: {
                  maxLength: 1024,
                },
              }}
              errorMessage={
                form.formState.errors[ProjectFormFields.DESCRIPTION]?.message
              }
              register={form.register}
            />
            <FormFieldComponent<CreateProjectFormData>
              formField={{
                name: ProjectFormFields.CLUSTER_ID,
                label: t('modal.create.form.cluster.label'),
                isRequired: true,
                placeholder: t('modal.create.form.cluster.placeholder'),
                component: (formElemProps) => (
                  <FormSelect
                    data-testid="cluster-select"
                    placeholder={t('modal.create.form.cluster.placeholder')}
                    disabledKeys={onboardedClusters
                      .filter((c) => c.status === 'unhealthy')
                      .map((c) => c.id)}
                    disallowEmptySelection
                    {...formElemProps}
                  >
                    {onboardedClusters.map((cluster: Cluster) => (
                      <SelectItem
                        data-testid={cluster.id}
                        key={cluster.id}
                        textValue={cluster.name}
                      >
                        {cluster.name}
                      </SelectItem>
                    ))}
                  </FormSelect>
                ),
              }}
              form={form}
              register={form.register}
            />
            <ProjectWorkloadPreemption form={form} t={t} />
          </div>
        );
      }}
    ></DrawerForm>
  );
};

export default CreateProjectModal;
