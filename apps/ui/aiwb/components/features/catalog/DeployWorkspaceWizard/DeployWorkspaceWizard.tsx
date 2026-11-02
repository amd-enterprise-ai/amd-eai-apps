// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  LinkToast,
  ManagedForm,
  selectiveZodResolver,
  Wizard,
} from '@amdenterpriseai/components';
import { useQuery } from '@tanstack/react-query';
import type { Resolver } from 'react-hook-form';
import { useTranslation } from 'next-i18next';
import type { ZodType, ZodTypeDef } from 'zod';

import { useProject } from '@/contexts/ProjectContext';
import { getChart } from '@/lib/app/charts';
import { getClusterResources } from '@/lib/app/cluster';
import { fetchProjectSecrets } from '@/lib/app/secrets';
import { deployWorkspace } from '@/lib/app/workloads';
import type { components } from '@/types/api';
import type { SecretResponseData } from '@/types/secrets';
import { toSecretNames } from '@/utils/secrets';
import type {
  WorkspaceCatalogItem,
  WorkspaceDeploymentPayload as CatalogItemDeployment,
} from '@/types/workspaces';
import { SecretUseCase } from '@amdenterpriseai/types';
import { useSystemToast } from '@amdenterpriseai/hooks';
import { bytesToGigabytes } from '@amdenterpriseai/utils/app';

import {
  createSettingsStepSchema,
  SettingsStepFields,
  SettingsStepSummary,
} from './steps/SettingsStep';
import {
  createTargetStepSchema,
  TargetStepFields,
  TargetStepSummary,
} from './steps/TargetStep';
import type { DeployWorkspaceFormValues } from './types';

const CLUSTER_RESOURCES_STALE_TIME_MS = 30_000;

type Props = {
  onClose: () => void;
  onDeploying?: () => void;
  catalogItem: WorkspaceCatalogItem;
  enableResourceAllocation?: boolean;
};

export const DeployWorkspaceWizard = ({
  enableResourceAllocation = true,
  onClose,
  onDeploying,
  catalogItem,
}: Props) => {
  const { t } = useTranslation('catalog');
  const { toast } = useSystemToast();
  const { activeProject: activeProjectId, projectUrl } = useProject();
  const {
    data: clusterResourcesData,
    isLoading: isLoadingClusterResources,
    isFetching: isFetchingClusterResources,
  } = useQuery({
    queryKey: ['cluster', 'resources'],
    queryFn: () => getClusterResources().then((response) => response.data),
    staleTime: CLUSTER_RESOURCES_STALE_TIME_MS,
  });

  const { data: catalogItemData, isFetching: isFetchingCatalogItem } = useQuery<
    components['schemas']['ChartResponse']
  >({
    queryKey: ['catalogItem', catalogItem.id],
    queryFn: () => getChart(catalogItem.id),
    enabled: !!catalogItem.id,
    staleTime: Infinity,
  });

  const { data: secretsData } = useQuery<SecretResponseData[]>({
    queryKey: ['secrets', activeProjectId, SecretUseCase.IMAGE_PULL_SECRET],
    queryFn: async () => {
      const response = await fetchProjectSecrets(
        activeProjectId!,
        SecretUseCase.IMAGE_PULL_SECRET,
      );
      return response.data;
    },
    enabled: !!activeProjectId,
    initialData: [],
    refetchInterval: 10000,
  });

  const requiredResources = {
    gpus: Number(catalogItem.requiredResources?.gpuCount) || 0,
    memoryPerGpu: Number(catalogItem.requiredResources?.systemMemory) || 0,
    cpuPerGpu: Number(catalogItem.requiredResources?.cpuCoreCount) || 0,
  };

  const availableResources = {
    gpus: clusterResourcesData?.availableResources.gpuCount ?? 0,
    memory: Math.floor(
      bytesToGigabytes(
        clusterResourcesData?.availableResources.memoryBytes ?? 0,
      ),
    ),
    cpu: (clusterResourcesData?.availableResources.cpuMilliCores ?? 0) / 1000,
  };

  const allocationCalculationNotReady =
    isFetchingClusterResources ||
    isFetchingCatalogItem ||
    !clusterResourcesData;

  const settingsStepSchema = createSettingsStepSchema(t);
  const targetStepSchema = createTargetStepSchema(t);
  const formSchema = settingsStepSchema.merge(targetStepSchema);
  const defaultValues: DeployWorkspaceFormValues = {
    containerImage: catalogItemData?.signature?.image ?? '',
    imagePullSecrets: [],
    displayName: catalogItem.displayName ?? catalogItem.name ?? '',
    customizeResources: false,
    ...requiredResources,
  };

  const handleComplete = async (values: DeployWorkspaceFormValues) => {
    const customizeResources = values.customizeResources ?? false;

    if (
      !catalogItem.slug ||
      !['vscode', 'jupyterlab', 'comfyui', 'mlflow'].includes(catalogItem.slug)
    ) {
      toast.error(t('notifications.deployWorkload.error'));
      return;
    }

    const deploymentPayload: CatalogItemDeployment = {
      displayName: values.displayName,
      type: 'workspaces',
      template: catalogItem.slug as components['schemas']['WorkspaceType'],
      gpus: customizeResources
        ? (values.gpus ?? requiredResources.gpus)
        : requiredResources.gpus,
      memoryPerGpu: customizeResources
        ? (values.memoryPerGpu ?? requiredResources.memoryPerGpu)
        : requiredResources.memoryPerGpu,
      cpuPerGpu: customizeResources
        ? (values.cpuPerGpu ?? requiredResources.cpuPerGpu)
        : requiredResources.cpuPerGpu,
      image: values.containerImage ?? catalogItemData?.signature?.image ?? '',
      imagePullSecrets: toSecretNames(values.imagePullSecrets),
    };

    try {
      const data = await deployWorkspace(activeProjectId!, deploymentPayload);
      toast.success(
        <LinkToast
          message={t('notifications.deployWorkload.success')}
          href={projectUrl(`/workloads/${data.id}`)}
        />,
      );
      onDeploying?.();
      onClose();
    } catch (error) {
      toast.error(t('notifications.deployWorkload.error'));
      console.error(t('notifications.deployWorkload.error'), error);
    }
  };

  if (!activeProjectId) {
    return null;
  }

  return (
    <ManagedForm<DeployWorkspaceFormValues>
      key={catalogItem.id}
      validationSchema={formSchema}
      defaultValues={defaultValues}
      onFormSuccess={handleComplete}
      resolver={
        selectiveZodResolver as unknown as (
          schema: ZodType<DeployWorkspaceFormValues, ZodTypeDef, unknown>,
        ) => Resolver<DeployWorkspaceFormValues>
      }
      renderFields={(form) => {
        const values = { ...defaultValues, ...form.watch() };

        return (
          <Wizard
            title={t('deployModal.title')}
            description={t('deployModal.subtitle')}
            onClose={onClose}
            onComplete={() => form.handleSubmit(handleComplete)()}
          >
            <Wizard.Step
              id="settings"
              title={t('deployModal.steps.settings.label')}
              description={t('deployModal.steps.settings.subtitle')}
              canProceed={settingsStepSchema.safeParse(values).success}
              renderSummary={() => (
                <SettingsStepSummary
                  data={values}
                  imagePullSecrets={secretsData ?? []}
                />
              )}
            >
              <SettingsStepFields
                form={form}
                catalogItem={catalogItem}
                containerImage={catalogItemData?.signature?.image}
                isLoadingContainerImage={isFetchingCatalogItem}
                imagePullSecrets={secretsData ?? []}
              />
            </Wizard.Step>

            <Wizard.Step
              id="target"
              title={t('deployModal.steps.target.label')}
              description={t('deployModal.steps.target.subtitle')}
              isOptional
              canProceed={targetStepSchema.safeParse(values).success}
              renderSummary={() => (
                <TargetStepSummary
                  data={values}
                  requiredResources={requiredResources}
                />
              )}
            >
              <TargetStepFields
                form={form}
                requiredResources={requiredResources}
                availableResources={availableResources}
                enableResourceAllocation={enableResourceAllocation}
                isLoadingClusterResources={isLoadingClusterResources}
                allocationCalculationNotReady={allocationCalculationNotReady}
              />
            </Wizard.Step>
          </Wizard>
        );
      }}
    />
  );
};

DeployWorkspaceWizard.displayName = 'DeployWorkspaceWizard';
