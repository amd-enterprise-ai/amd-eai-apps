// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  ManagedForm,
  FormFieldComponent,
  FormSelect,
  SelectItem,
} from '@amdenterpriseai/components';
import { useSystemToast } from '@amdenterpriseai/hooks';
import { getCluster as fetchCluster, updateProject } from '@/services/app';
import {
  gpuPreemptionConfigFromFormData,
  gpuPreemptionConfigToFormFields,
  refineGpuPreemptionFormData,
} from '@/components/features/projects/gpu-preemption-form';
import { ProjectGpuPreemptionReadOnly } from '@/components/features/projects/ProjectGpuPreemptionReadOnly';
import { ProjectWorkloadPreemption } from '@/components/features/projects/ProjectWorkloadPreemption';
import { useAccessControl } from '@/hooks/useAccessControl';
import { Cluster } from '@/types/clusters';
import { GpuPreemptionPolicy } from '@/types/enums/gpu-preemption-policy';
import {
  ProjectFormFields,
  ProjectGpuPreemptionFormFields,
} from '@/types/enums/project-form-fields';
import {
  CreateProjectFormData,
  ProjectWithMembers,
  ProjectWithResourceAllocation,
  UpdateProjectRequest,
} from '@/types/projects';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'next-i18next';
import { useCallback, useMemo } from 'react';
import { z, ZodType } from 'zod';
import { APIRequestError } from '@amdenterpriseai/utils/app';
import { FormField } from '@amdenterpriseai/types';

interface Props {
  project: ProjectWithMembers;
  cluster: Cluster;
}

/** Remount ManagedForm when server preemption config changes; useForm ignores defaultValues prop updates. */
function serverGpuPreemptionSyncKey(
  gpu: ProjectWithMembers['gpuPreemption'],
): string {
  if (!gpu.enabled) {
    return 'disabled';
  }
  return `${gpu.policy}:${gpu.threshold}:${gpu.gracePeriod}`;
}

export const ProjectBasicInfoForm: React.FC<Props> = ({ project, cluster }) => {
  const { t } = useTranslation('projects');
  const { toast } = useSystemToast();
  const queryClient = useQueryClient();
  const { isAdministrator } = useAccessControl();

  const defaultValues = useMemo(
    (): CreateProjectFormData => ({
      [ProjectFormFields.NAME]: project.name,
      [ProjectFormFields.DESCRIPTION]: project.description,
      [ProjectFormFields.CLUSTER_ID]: project.clusterId,
      ...gpuPreemptionConfigToFormFields(project.gpuPreemption),
    }),
    [
      project.clusterId,
      project.description,
      project.gpuPreemption,
      project.name,
    ],
  );

  const managedFormSyncKey = useMemo(
    () => serverGpuPreemptionSyncKey(project.gpuPreemption),
    [project.gpuPreemption],
  );

  const { mutate: updateProjectMutation, isPending: isUpdatingProject } =
    useMutation<ProjectWithResourceAllocation, Error, UpdateProjectRequest>({
      mutationFn: updateProject,
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: ['project'] });
        queryClient.invalidateQueries({ queryKey: ['cluster'] });
        toast.success(t('settings.form.notification.success'));
      },
      onError: (error) => {
        toast.error(error.message, error as APIRequestError);
        console.error('Error saving project', error);
      },
    });

  const { data: clusterData } = useQuery<Cluster>({
    queryKey: ['cluster'],
    queryFn: () => fetchCluster(cluster.id as string),
    initialData: cluster,
  });

  const formSchema: ZodType<CreateProjectFormData> = useMemo(
    () =>
      z
        .object({
          [ProjectFormFields.NAME]: z.string(),
          [ProjectFormFields.DESCRIPTION]: z
            .string()
            .trim()
            .min(
              2,
              t('settings.form.basicInfo.description.validation.length') || '',
            )
            .max(
              1024,
              t('settings.form.basicInfo.description.validation.length') || '',
            ),
          [ProjectFormFields.CLUSTER_ID]: z.string().trim(),
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
    [t],
  );

  const projectFormFields: FormField<CreateProjectFormData>[] = [
    {
      name: ProjectFormFields.NAME,
      label: t('settings.form.basicInfo.name.label'),
      isReadOnly: true,
      props: {
        variant: 'primary' as const,
      },
    },
    {
      name: ProjectFormFields.DESCRIPTION,
      label: t('settings.form.basicInfo.description.label'),
      isRequired: true,
      placeholder: t('settings.form.basicInfo.description.placeholder'),
      props: {
        variant: 'primary' as const,
        maxLength: 1024,
      },
    },
    {
      name: ProjectFormFields.CLUSTER_ID,
      label: t('settings.form.basicInfo.cluster.label'),
      isRequired: false,
      component: (formElemProps) => (
        <FormSelect
          data-testid="cluster-select"
          variant="primary"
          {...formElemProps}
          isDisabled
        >
          <SelectItem data-testid={clusterData.id} key={clusterData.id}>
            {clusterData.name}
          </SelectItem>
        </FormSelect>
      ),
    },
  ];

  const handleFormSubmit = useCallback(
    (data: CreateProjectFormData) => {
      const projectDescription = (
        data[ProjectFormFields.DESCRIPTION] as string
      ).trim();

      const gpuPreemption = gpuPreemptionConfigFromFormData(data);

      updateProjectMutation({
        id: project.id,
        description: projectDescription,
        quota: {
          cpuMilliCores: project.quota.cpuMilliCores,
          gpuCount: project.quota.gpuCount,
          memoryBytes: project.quota.memoryBytes,
          ephemeralStorageBytes: project.quota.ephemeralStorageBytes,
        },
        gpuPreemption,
      });
    },
    [project, updateProjectMutation],
  );

  if (!isAdministrator) {
    const preemption = project.gpuPreemption;
    return (
      <div className="w-full flex flex-col">
        <section id="basic-info">
          <div className="flex flex-col gap-6 my-3">
            <div className="flex flex-col gap-4">
              <div>
                <div className="text-sm mb-1">
                  {t('settings.form.basicInfo.name.label')}
                </div>
                <div>{project.name}</div>
              </div>
              <div>
                <div className="text-sm mb-1">
                  {t('settings.form.basicInfo.description.label')}
                </div>
                <div>{project.description}</div>
              </div>
              <div>
                <div className="text-sm mb-1">
                  {t('settings.form.basicInfo.cluster.label')}
                </div>
                <div>{clusterData.name}</div>
              </div>
            </div>
          </div>
        </section>
        <ProjectGpuPreemptionReadOnly config={preemption} t={t} />
      </div>
    );
  }

  return (
    <ManagedForm<CreateProjectFormData>
      key={managedFormSyncKey}
      isActioning={isUpdatingProject}
      className="flex flex-col w-full"
      defaultValues={defaultValues}
      validationSchema={formSchema}
      showSubmitButton={true}
      showResetButton={true}
      submitButtonText={t('settings.form.actions.confirm')!}
      resetButtonText={t('settings.form.actions.reset')!}
      onFormSuccess={handleFormSubmit}
      renderFields={(form) => (
        <div className="w-full flex flex-col">
          <section id="basic-info">
            <div className="flex flex-col gap-6 my-3">
              <div className="flex flex-col gap-4">
                {projectFormFields.map((field) => (
                  <FormFieldComponent<CreateProjectFormData>
                    key={field.name}
                    formField={field}
                    errorMessage={form.formState.errors[field.name]?.message}
                    form={form}
                    defaultValue={
                      defaultValues[
                        field.name as keyof CreateProjectFormData
                      ] as string | undefined
                    }
                  />
                ))}
              </div>
            </div>
          </section>
          <ProjectWorkloadPreemption form={form} t={t} />
        </div>
      )}
    />
  );
};

export default ProjectBasicInfoForm;
