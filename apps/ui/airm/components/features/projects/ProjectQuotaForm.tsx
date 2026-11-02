// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { Alert, ManagedForm } from '@amdenterpriseai/components';
import { QuotaAllocationEditFields } from '@/types/enums/quotas-form-fields';
import { ProjectQuotaFormData } from '@/types/projects';
import { UpdateProjectRequest } from '@/types/projects';
import { convertStringToNumber } from '@amdenterpriseai/utils/app';
import { useTranslation } from 'next-i18next';
import { useCallback, useMemo } from 'react';
import { z } from 'zod';
import { AllocationSettings } from '../quotas';
import { Cluster } from '@/types/clusters';
import {
  ProjectWithMembers,
  ProjectWithResourceAllocation,
} from '@/types/projects';
import { UpdateQuotaRequest } from '@/types/quotas';
import { gigabytesToBytes } from '@amdenterpriseai/utils/app';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { APIRequestError } from '@amdenterpriseai/utils/app';
import { useSystemToast } from '@amdenterpriseai/hooks';
import { useAccessControl } from '@/hooks/useAccessControl';
import { updateProject } from '@/services/app';

interface Props {
  project: ProjectWithMembers;
  cluster: Cluster;
}

const tranlationKeySet = 'projects';

export const ProjectQuotaForm: React.FC<Props> = ({ project, cluster }) => {
  const { t } = useTranslation(tranlationKeySet);
  const { toast } = useSystemToast();
  const queryClient = useQueryClient();
  const { isAdministrator } = useAccessControl();

  const defaultValues = useMemo(
    (): ProjectQuotaFormData => ({
      [QuotaAllocationEditFields.CPU]: project.quota.cpuMilliCores / 1000,
      [QuotaAllocationEditFields.GPU]: project.quota.gpuCount,
      [QuotaAllocationEditFields.RAM]: Math.floor(
        project.quota.memoryBytes / (1024 * 1024 * 1024),
      ),
      [QuotaAllocationEditFields.DISK]: Math.floor(
        project.quota.ephemeralStorageBytes / (1024 * 1024 * 1024),
      ),
    }),
    [
      project.id,
      project.quota.cpuMilliCores,
      project.quota.ephemeralStorageBytes,
      project.quota.gpuCount,
      project.quota.memoryBytes,
    ],
  );

  const formSchema = useMemo(
    () =>
      z.object({
        [QuotaAllocationEditFields.CPU]: z
          .preprocess((val) => {
            return convertStringToNumber(val as string);
          }, z.number())
          .default(0),
        [QuotaAllocationEditFields.GPU]: z.preprocess((val) => {
          return convertStringToNumber(val as string);
        }, z.number()),
        [QuotaAllocationEditFields.RAM]: z.preprocess((val) => {
          return convertStringToNumber(val as string);
        }, z.number()),
        [QuotaAllocationEditFields.DISK]: z.preprocess((val) => {
          return convertStringToNumber(val as string);
        }, z.number()),
      }) as z.ZodType<ProjectQuotaFormData, z.ZodTypeDef, ProjectQuotaFormData>,
    [],
  );

  const { mutate: updateProjectMutation, isPending: isUpdatingProject } =
    useMutation<
      ProjectWithResourceAllocation,
      Error,
      UpdateProjectRequest,
      { previousProject?: ProjectWithMembers }
    >({
      mutationFn: updateProject,
      onMutate: async (variables) => {
        await queryClient.cancelQueries({ queryKey: ['project'] });
        const previousProject = queryClient.getQueryData<ProjectWithMembers>([
          'project',
        ]);
        if (previousProject) {
          queryClient.setQueryData<ProjectWithMembers>(['project'], {
            ...previousProject,
            quota: { ...previousProject.quota, ...variables.quota },
          });
        }
        return { previousProject };
      },
      onError: (error, _variables, context) => {
        if (context?.previousProject) {
          queryClient.setQueryData(['project'], context.previousProject);
        }
        toast.error(error.message, error as APIRequestError);
        console.error('Error saving project', error);
      },
      onSuccess: () => {
        toast.success(t('settings.form.notification.success'));
      },
      onSettled: () => {
        queryClient.invalidateQueries({ queryKey: ['project'] });
        queryClient.invalidateQueries({ queryKey: ['cluster'] });
      },
    });

  // Unified handler for both basic info and quota forms
  const handleFormSubmit = useCallback(
    (data: ProjectQuotaFormData) => {
      const quota: UpdateQuotaRequest = {
        cpuMilliCores: data[QuotaAllocationEditFields.CPU] * 1000,
        memoryBytes: gigabytesToBytes(data[QuotaAllocationEditFields.RAM]),
        ephemeralStorageBytes: gigabytesToBytes(
          data[QuotaAllocationEditFields.DISK],
        ),
        gpuCount: data[QuotaAllocationEditFields.GPU] ?? 0,
      };

      updateProjectMutation({
        id: project.id,
        description: project.description,
        quota,
        gpuPreemption: project.gpuPreemption,
      });
    },
    [project, updateProjectMutation],
  );

  return (
    <ManagedForm<ProjectQuotaFormData>
      isActioning={isUpdatingProject}
      className="flex flex-col w-full"
      defaultValues={defaultValues}
      validationSchema={formSchema}
      showSubmitButton={isAdministrator}
      showResetButton={isAdministrator}
      submitButtonText={t('settings.form.actions.confirm')!}
      resetButtonText={t('settings.form.actions.reset')!}
      onFormSuccess={handleFormSubmit}
      renderFields={(form) => (
        <div className="w-full flex flex-col">
          <section id="guaranteed-quota">
            <div className="flex flex-col gap-6 my-3">
              <Alert
                status="accent"
                description={t('settings.form.guaranteedQuota.info')}
              />
              <AllocationSettings
                form={form}
                quota={project.quota}
                cluster={cluster}
                isReadonly={!isAdministrator}
              />
            </div>
          </section>
        </div>
      )}
    />
  );
};

export default ProjectQuotaForm;
