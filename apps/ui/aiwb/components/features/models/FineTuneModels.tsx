// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  IconAffiliate,
  IconCpu,
  IconEye,
  IconRocket,
  IconTrash,
} from '@tabler/icons-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { useTranslation } from 'next-i18next';

import { useOverlayState, useSystemToast } from '@amdenterpriseai/hooks';

import {
  cancelFineTuningJob,
  deleteModel,
  finetuneModel,
  getFinetunableModels,
  listAllProjectFineTunedModels,
} from '@/lib/app/models';
import {
  AIM_MODEL_NAME_LABEL,
  AIM_MODEL_SOURCE_DESCRIPTION_ANNOTATION,
  AIM_MODEL_TRAINING_OUTPUT_ANNOTATION,
  AIM_MODEL_WORKLOAD_ID_LABEL,
  AIMService,
} from '@/types/aims';
import type { components } from '@/types/api';
import { SUBMITTER_ANNOTATION } from '@/types/artifacts';
import { ModelFinetuneParams } from '@/types/models';
import { resolveBaseModelSource } from '@/lib/app/aims';
import { listAllWorkloads } from '@/lib/app/workloads';
import { listAllInferenceDeployments } from '@/lib/app/inference';
import { APIRequestError } from '@amdenterpriseai/utils/app';

import { getFilteredData } from '@amdenterpriseai/utils/app';
import { getWorkloadStatusVariants } from '@/utils/workloads';

import {
  ActionButton,
  ActionsToolbar,
  ClientSideDataTable,
  DateDisplay,
  LinkToast,
  NoDataDisplay,
  StatusDisplay,
} from '@amdenterpriseai/components';
import { ActionItem, TableColumns } from '@amdenterpriseai/types';
import { FilterComponentType } from '@amdenterpriseai/types';
import { SortDirection } from '@amdenterpriseai/types';
import type { ResourceStatus } from '@/types/workloads';
import { ClientSideDataFilter, FilterValueMap } from '@amdenterpriseai/types';
import { FinetunableModel, Model } from '@/types/models';

import DeleteModelModal from '@/components/features/models/DeleteModelModal';
import { DeployCustomAIMDrawer } from '@/components/features/models/DeployCustomAIMDrawer';
import { FinetuneWizard } from '@/components/features/models/FinetuneWizard';
import { TruncatedDescription } from '@/components/shared/TruncatedDescription';
import ModelDetailsModal from '@/components/features/models/ModelDetailsModal';
import DeleteWorkloadModal from '@/components/features/workloads/DeleteWorkloadModal';

import { useProject } from '@/contexts/ProjectContext';
import { useRouter } from 'next/router';
import type { Workload } from '@/types/workloads';

const ModelsTableField = {
  NAME: 'name',
  CREATED_AT: 'createdAt',
  CREATED_BY: 'createdBy',
  ONBOARDING_STATUS: 'onboardingStatus',
  STATUS: 'status',
  WORKLOADS: 'workloads',
} as const;

type ModelsTableField =
  (typeof ModelsTableField)[keyof typeof ModelsTableField];

type ModelRow = Model & {
  description?: string;
  output?: string | null;
  source: 'model' | 'workload';
};

const fineTuningTypeTranslationKeys: Record<
  string,
  | 'list.fineTuningTypes.full'
  | 'list.fineTuningTypes.lora'
  | 'list.fineTuningTypes.merged'
> = {
  full: 'list.fineTuningTypes.full',
  lora: 'list.fineTuningTypes.lora',
  merged: 'list.fineTuningTypes.merged',
};

// Mirror the statuses fetched by the workloads query below: STARTING is a
// real fine-tuning state and must be visible by default, otherwise jobs that
// have left PENDING but haven't reached RUNNING get hidden in the UI even
// though the server returned them.
const defaultStatusSet: ResourceStatus[] = [
  'Pending',
  'Starting',
  'Running',
  'Complete',
  'Failed',
];

const convertFilterValueMap = (
  filters: FilterValueMap,
): ClientSideDataFilter<ModelRow>[] => {
  const newFilters: ClientSideDataFilter<ModelRow>[] = [];
  if (filters?.search) {
    newFilters.push({
      field: 'name',
      values: filters.search,
    });
  }
  if (filters?.status && filters.status.length > 0) {
    newFilters.push({
      field: 'status',
      values: filters.status,
    });
  }
  return newFilters;
};

const FineTuneModels = () => {
  const { t } = useTranslation('models');
  const { t: tCustomModels } = useTranslation('models', {
    keyPrefix: 'customModels',
  });
  const { t: tWorkloads } = useTranslation('workloads');
  const router = useRouter();
  const queryClient = useQueryClient();
  const { toast } = useSystemToast();
  const { activeProject, projectPath } = useProject();

  const [modelForDeletion, setModelForDeletion] = useState<Model | undefined>(
    undefined,
  );
  const [workloadForDeletion, setWorkloadForDeletion] = useState<
    Workload | undefined
  >(undefined);
  const [hasActiveDeployments, setHasActiveDeployments] = useState(false);
  const [modelForAIMDeploy, setModelForAIMDeploy] = useState<ModelRow | null>(
    null,
  );
  const [modelToFinetune, setModelToFinetune] = useState<Model | undefined>(
    undefined,
  );

  const finetuneDisclosure = useOverlayState();

  const { data: finetunableModels } = useQuery({
    queryKey: ['models', 'finetunable'],
    queryFn: (): Promise<FinetunableModel[]> => getFinetunableModels(),
  });

  const deleteModelDisclosure = useOverlayState();
  const deleteWorkloadDisclosure = useOverlayState();

  const [filters, setFilters] = useState<ClientSideDataFilter<ModelRow>[]>(
    convertFilterValueMap({
      status: defaultStatusSet,
    }),
  );

  const {
    data: rawModels,
    isLoading: isModelsLoading,
    isRefetching: isModelsRefetching,
    refetch: refetchModels,
    error: modelsError,
    dataUpdatedAt: modelsDataUpdatedAt,
  } = useQuery<components['schemas']['AIMModelResource'][]>({
    queryKey: ['project', activeProject, 'models', 'fine-tuned'],
    queryFn: () => listAllProjectFineTunedModels(activeProject!),
    refetchInterval: 30000,
    enabled: !!activeProject,
  });

  const models: ModelRow[] = useMemo(
    () =>
      (rawModels ?? []).map((item) => {
        const labels = item.metadata.labels ?? {};
        const annotations = item.metadata.annotations ?? {};
        const sourceModelSource = resolveBaseModelSource(item);
        const sourceModelId = sourceModelSource?.modelId || '';
        // Fall back to the source recipe when the model's own image metadata
        // omits the token requirement (common for fine-tuned models).
        const recipeTokenRequired = finetunableModels?.find(
          (m) => m.canonicalName === sourceModelId,
        )?.hfTokenRequired;
        const hfTokenRequired =
          item.status?.imageMetadata?.model?.hfTokenRequired ??
          recipeTokenRequired;

        return {
          id: labels[AIM_MODEL_WORKLOAD_ID_LABEL],
          name: labels[AIM_MODEL_NAME_LABEL] || item.metadata.name,
          canonicalName: sourceModelId,
          description: annotations[AIM_MODEL_SOURCE_DESCRIPTION_ANNOTATION],
          sourceUri: sourceModelSource?.sourceUri,
          resourceName: item.metadata.name,
          createdBy: annotations[SUBMITTER_ANNOTATION],
          hfTokenRequired,
          output: annotations[AIM_MODEL_TRAINING_OUTPUT_ANNOTATION],
          source: 'model' as const,
          status: (() => {
            switch (item.status?.status) {
              case 'Ready':
                return 'Complete';
              case 'Failed':
              case 'Degraded':
                return 'Failed';
              default:
                return 'Pending';
            }
          })(),
          workloadId: labels[AIM_MODEL_WORKLOAD_ID_LABEL],
          createdAt: item.metadata?.creationTimestamp ?? undefined,
        };
      }),
    [rawModels, finetunableModels],
  );

  const {
    data: workloads,
    isLoading: isWorkloadsLoading,
    isRefetching: isWorkloadsRefetching,
    refetch: refetchWorkloads,
    dataUpdatedAt: workloadsDataUpdatedAt,
  } = useQuery({
    queryKey: ['project', activeProject, 'workloads'],
    queryFn: async () => {
      if (!activeProject) return [];

      return await listAllWorkloads(activeProject, {
        workloadType: ['FINE_TUNING'],
        // No need to show the deleted workloads in the table.
        statusFilter: ['Pending', 'Starting', 'Running', 'Complete', 'Failed'],
      });
    },
    refetchInterval: 30000, // Refetch every 30 seconds
    enabled: !!activeProject,
  });

  const {
    data: aimServices = [],
    isRefetching: isAimServicesRefetching,
    refetch: refetchAimServices,
    dataUpdatedAt: aimServicesDataUpdatedAt,
  } = useQuery<AIMService[]>({
    queryKey: ['project', activeProject, 'aim-services'],
    queryFn: () => listAllInferenceDeployments(activeProject!),
    refetchInterval: 30000,
    enabled: !!activeProject,
  });

  const dataUpdatedAt = Math.max(
    modelsDataUpdatedAt ?? 0,
    workloadsDataUpdatedAt ?? 0,
    aimServicesDataUpdatedAt ?? 0,
  );

  const refetchModelsAndWorkloads = useCallback(async () => {
    await Promise.all([
      refetchModels(),
      refetchWorkloads(),
      refetchAimServices(),
    ]);
  }, [refetchModels, refetchWorkloads, refetchAimServices]);

  const deleteModelMutation = useMutation({
    mutationFn: async (variables: { name: string; force?: boolean }) => {
      if (!activeProject) {
        throw new Error('No active project selected');
      }
      await deleteModel(variables.name, activeProject, variables.force);
    },
    onSuccess: () => {
      setHasActiveDeployments(false);
      queryClient.invalidateQueries({
        queryKey: ['project', activeProject, 'models'],
      });
      queryClient.invalidateQueries({
        queryKey: ['project', activeProject, 'workloads'],
      });
      toast.success(
        t(
          'customModels.list.actions.delete.notification.success',
          'Model deleted successfully',
        ),
      );
      deleteModelDisclosure.onClose();
    },
    onError: (error: unknown) => {
      if (error instanceof APIRequestError && error.statusCode === 409) {
        setHasActiveDeployments(true);
        return;
      }
      deleteModelDisclosure.onClose();
      const message =
        error instanceof APIRequestError ? error.message : undefined;
      toast.error(
        message ||
          t(
            'customModels.list.actions.delete.notification.error',
            'Error deleting model',
          ),
      );
      console.error('Error deleting model:', error);
    },
  });

  const deleteWorkloadMutation = useMutation({
    mutationFn: async (id: string) => {
      if (!activeProject) {
        throw new Error('No active project selected');
      }
      // Synthesized rows here represent in-progress FINE_TUNING workloads
      // (see inProgressFinetuningModels above), so cancel via the fine-tuning
      // capability endpoint. Generic /workloads DELETE was removed.
      await cancelFineTuningJob(id, activeProject);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ['project', activeProject, 'models'],
      });
      queryClient.invalidateQueries({
        queryKey: ['project', activeProject, 'workloads'],
      });
      toast.success(
        t(
          'customModels.list.actions.delete.workloadNotification.success',
          'Workload deleted successfully',
        ),
      );
      deleteWorkloadDisclosure.onClose();
    },
    onError: (error: unknown) => {
      const message =
        error instanceof APIRequestError ? error.message : undefined;
      toast.error(
        message ||
          t(
            'customModels.list.actions.delete.notification.error',
            'Error deleting workload',
          ),
      );
      console.error('Error deleting workload:', error);
    },
  });

  const handleOpenDeleteModal = useCallback(
    (item: ModelRow) => {
      if (item.source === 'model') {
        setModelForDeletion(item);
        setHasActiveDeployments(false);
        deleteModelDisclosure.onOpen();
      } else {
        setWorkloadForDeletion({
          id: item.workloadId!,
          name: item.resourceName || item.name,
          displayName: item.canonicalName,
        } as Workload);
        deleteWorkloadDisclosure.onOpen();
      }
    },
    [deleteModelDisclosure, deleteWorkloadDisclosure],
  );

  const finetuneModelMutation = useMutation({
    mutationFn: async (variables: {
      id: string;
      params: ModelFinetuneParams;
    }) => {
      if (!activeProject) {
        throw new Error('No active project selected');
      }
      return finetuneModel(variables.id, variables.params, activeProject);
    },
    onSuccess: (_data, variables) => {
      const isLora = variables.params.output === 'adapter';
      queryClient.invalidateQueries({
        queryKey: ['project', activeProject, 'models'],
      });
      if (isLora) {
        queryClient.invalidateQueries({
          queryKey: ['project', activeProject, 'artifacts'],
        });
      }
      toast.success(
        <LinkToast
          message={t('finetuneWizard.notifications.success')}
          href={projectPath(
            isLora ? '/fine-tuning/loras' : '/fine-tuning/models',
          )}
          linkLabel={t(
            isLora
              ? 'finetuneWizard.notifications.viewLoras'
              : 'finetuneWizard.notifications.viewModels',
          )}
        />,
      );
      finetuneDisclosure.onClose();
    },
    onError: (error) => {
      toast.error(t('finetuneWizard.notifications.error'));
      console.error('Error fine-tuning model:', error);
    },
  });

  const handleOpenFinetuneModal = useCallback(
    (model?: Model) => {
      setModelToFinetune(model);
      finetuneDisclosure.onOpen();
    },
    [finetuneDisclosure],
  );

  // Count active workloads per model from two sources:
  // - Fine-tuning jobs (STARTING/PENDING/RUNNING): keyed by workload.id → matches model.id (AIM_MODEL_WORKLOAD_ID_LABEL)
  // - AIM service deployments: keyed by resolvedModel name → matches model.resourceName
  const workloadsCount = useMemo(() => {
    const countMap = new Map<string, number>();
    if (workloads) {
      workloads.forEach((workload) => {
        if (
          workload.type === 'FINE_TUNING' &&
          (workload.status === 'Starting' ||
            workload.status === 'Pending' ||
            workload.status === 'Running')
        ) {
          countMap.set(workload.id, (countMap.get(workload.id) || 0) + 1);
        }
      });
    }
    aimServices.forEach((aim) => {
      const modelName = aim.spec?.model?.name;
      if (modelName) {
        countMap.set(modelName, (countMap.get(modelName) || 0) + 1);
      }
    });
    return countMap;
  }, [workloads, aimServices]);

  // Synthesize in-progress fine-tuning workloads as Model objects so they
  // appear in the table even before an AIMModel CR is created.
  const inProgressFinetuningModels = useMemo<ModelRow[]>(() => {
    if (!workloads || !models) return [];
    const completedResourceNames = new Set(
      models.map((m) => m.resourceName).filter(Boolean),
    );
    return workloads
      .filter(
        (w) =>
          w.type === 'FINE_TUNING' &&
          w.status !== 'Complete' &&
          w.annotations?.[AIM_MODEL_TRAINING_OUTPUT_ANNOTATION] !== 'lora' &&
          !completedResourceNames.has(w.name),
      )
      .map((w) => ({
        id: w.id,
        name: w.displayName || w.name,
        canonicalName: '',
        description: w.annotations?.[AIM_MODEL_SOURCE_DESCRIPTION_ANNOTATION],
        createdAt: w.createdAt,
        createdBy: w.createdBy ?? undefined,
        resourceName: w.name,
        source: 'workload' as const,
        status: w.status,
        workloadId: w.id,
        output: w.annotations?.[AIM_MODEL_TRAINING_OUTPUT_ANNOTATION],
      }));
  }, [workloads, models]);

  const filteredModels = useMemo(() => {
    const completedModels = (models ?? []).map((model) => {
      const matchingWorkload = workloads?.find(
        (workload) => workload.id === model.workloadId,
      );
      return {
        ...model,
        createdBy: model.createdBy ?? matchingWorkload?.createdBy ?? undefined,
      };
    });
    const allModels = [...inProgressFinetuningModels, ...completedModels];
    if (allModels.length === 0) return [];

    const filteredModels = getFilteredData(allModels, filters);
    return filteredModels.reduce<
      (ModelRow & { [ModelsTableField.WORKLOADS]: number })[]
    >((result, model) => {
      const ftCount = model.id ? workloadsCount.get(model.id) || 0 : 0;
      const aimCount = model.resourceName
        ? workloadsCount.get(model.resourceName) || 0
        : 0;
      result.push({
        ...model,
        [ModelsTableField.WORKLOADS]: ftCount + aimCount,
      });

      return result;
    }, []);
  }, [models, workloads, inProgressFinetuningModels, filters, workloadsCount]);

  const {
    isOpen: isModelDetailsModalOpen,
    onOpen: onModelDetailsModalOpen,
    onOpenChange: onModelDetailsModalOpenChange,
  } = useOverlayState();

  const [modelBeingSelected, setModelBeingSelected] = useState<
    components['schemas']['AIMModelResource'] | undefined
  >(undefined);

  const statusFilterItems = useMemo(
    () => [
      {
        key: 'Pending',
        label: t('status.pending'),
      },
      {
        key: 'Starting',
        label: t('status.starting'),
      },
      {
        key: 'Running',
        label: t('status.running'),
      },
      {
        key: 'Complete',
        label: t('status.complete'),
      },
      {
        key: 'Failed',
        label: t('status.failed'),
      },
    ],
    [t],
  );

  useEffect(() => {
    if (modelsError) {
      toast.error(
        t('notifications.refresh.error', {
          error: String(modelsError.message),
        }),
      );
    }
  }, [modelsError, toast, t]);

  const columns: TableColumns<ModelsTableField> = [
    {
      key: ModelsTableField.NAME,
      sortable: true,
      className: 'w-full min-w-64 max-w-0',
    },
    {
      key: ModelsTableField.STATUS,
      sortable: true,
      className: 'w-0 whitespace-nowrap',
    },
    {
      key: ModelsTableField.WORKLOADS,
      sortable: true,
      className: 'w-0 whitespace-nowrap',
    },
    {
      key: ModelsTableField.CREATED_AT,
      sortable: true,
      className: 'w-0 whitespace-nowrap',
    },
    {
      key: ModelsTableField.CREATED_BY,
      sortable: true,
      className: 'w-0 whitespace-nowrap',
    },
  ];

  const actions = (item: ModelRow) => {
    const actionsList: ActionItem<ModelRow>[] = [
      {
        key: 'details',
        color: 'default',
        startContent: <IconEye />,
        onPress: (m: ModelRow) => {
          if (m.source === 'workload') {
            router.push({
              pathname: projectPath(`/workloads/${m.workloadId}`),
              query: { ref: router.asPath },
            });
          } else {
            const raw = rawModels?.find(
              (r) => r.metadata.name === m.resourceName,
            );
            setModelBeingSelected(raw);
            onModelDetailsModalOpen();
          }
        },
        label: t('customModels.list.actions.details.label'),
      },
    ];

    if (item.status === 'Complete') {
      if (item.source === 'model' && item.id) {
        actionsList.push({
          key: 'finetune',
          color: 'default',
          startContent: <IconAffiliate />,
          onPress: (model: ModelRow) => {
            handleOpenFinetuneModal(model);
          },
          label: t('customModels.list.actions.finetune.label'),
        });
      }

      actionsList.push({
        key: 'deploy',
        color: 'default',
        startContent: <IconRocket />,
        onPress: (model: ModelRow) => {
          setModelForAIMDeploy(model);
        },
        label: t('customModels.list.actions.deploy.label'),
      });
    }

    actionsList.push({
      key: 'delete',
      color: 'danger',
      startContent: <IconTrash />,
      onPress: (m: ModelRow) => {
        handleOpenDeleteModal(m);
      },
      label: t('customModels.list.actions.delete.label'),
    });
    return actionsList;
  };

  const customRenderers: Partial<
    Record<ModelsTableField, (item: ModelRow) => React.ReactNode | string>
  > = {
    [ModelsTableField.NAME]: (item: ModelRow) => {
      const description = item.description?.trim();
      const canonicalName = item.canonicalName?.trim();
      const translationKey =
        fineTuningTypeTranslationKeys[item.output ?? 'full'];
      const fineTuningType = translationKey
        ? tCustomModels(translationKey)
        : undefined;
      const hasMetadata = canonicalName || fineTuningType;

      return (
        <div className="flex min-w-0 flex-col gap-1">
          <span>{item.name}</span>
          {description ? (
            <TruncatedDescription description={description} />
          ) : null}
          {hasMetadata ? (
            <span className="flex min-w-0 items-center gap-1 text-xs text-muted">
              {canonicalName ? (
                <span className="inline-flex shrink-0 items-center gap-0.5">
                  <IconCpu size={14} aria-hidden />
                  {canonicalName}
                </span>
              ) : null}
              {canonicalName && fineTuningType ? (
                <span aria-hidden>•</span>
              ) : null}
              {fineTuningType ? (
                <span className="inline-flex shrink-0 items-center gap-0.5">
                  <IconAffiliate size={14} aria-hidden />
                  {fineTuningType}
                </span>
              ) : null}
            </span>
          ) : null}
        </div>
      );
    },
    [ModelsTableField.STATUS]: (item: ModelRow) => (
      <StatusDisplay
        type={item[ModelsTableField.STATUS] as ResourceStatus}
        variants={getWorkloadStatusVariants(tWorkloads)}
      />
    ),
    [ModelsTableField.CREATED_AT]: (item: ModelRow) =>
      item.createdAt ? (
        <DateDisplay date={item.createdAt} />
      ) : (
        <NoDataDisplay />
      ),
    [ModelsTableField.CREATED_BY]: (item: ModelRow) =>
      item.createdBy || <NoDataDisplay />,
  };

  const filterConfig = useMemo(
    () => ({
      search: {
        name: 'search',
        label: t('customModels.list.filters.search.placeholder'),
        placeholder: t('customModels.list.filters.search.placeholder'),
        type: FilterComponentType.TEXT,
      },
      status: {
        name: 'status',
        label: t('customModels.list.filters.status.label'),
        placeholder: t('customModels.list.filters.status.placeholder'),
        type: FilterComponentType.DROPDOWN,
        defaultSelectedValues: defaultStatusSet,
        fields: statusFilterItems,
      },
    }),
    [t, statusFilterItems],
  );

  const handleFilterChange = (filters: FilterValueMap) => {
    const newFilters: ClientSideDataFilter<ModelRow>[] =
      convertFilterValueMap(filters);
    setFilters(newFilters);
  };

  return (
    <div data-testid="fine-tune-models" className="flex flex-col w-full">
      <ActionsToolbar
        filterConfig={filterConfig}
        onFilterChange={handleFilterChange}
        onRefresh={refetchModelsAndWorkloads}
        updatedTimestamp={dataUpdatedAt}
        isRefreshing={
          isModelsLoading ||
          isWorkloadsLoading ||
          isModelsRefetching ||
          isWorkloadsRefetching ||
          isAimServicesRefetching
        }
        endContent={
          <ActionButton
            primary
            isDisabled={isModelsLoading || isWorkloadsLoading}
            onPress={() => handleOpenFinetuneModal(undefined)}
            icon={<IconAffiliate size={16} stroke={3} />}
            data-testid="fine-tune-models-finetune"
          >
            {t('customModels.list.actions.finetune.title')}
          </ActionButton>
        }
      />

      <ClientSideDataTable
        data={filteredModels}
        columns={columns}
        className="flex-1 overflow-y-auto"
        defaultSortByField={ModelsTableField.NAME}
        defaultSortDirection={SortDirection.ASC}
        customRenderers={
          customRenderers as Record<string, (item: unknown) => React.ReactNode>
        }
        isLoading={isModelsLoading || isWorkloadsLoading}
        isFetching={isModelsRefetching}
        translation={tCustomModels}
        idKey={'resourceName' as never}
        rowActions={actions}
      />

      <ModelDetailsModal
        onOpenChange={onModelDetailsModalOpenChange}
        isOpen={isModelDetailsModalOpen}
        model={modelBeingSelected}
      />

      <DeleteModelModal
        isOpen={deleteModelDisclosure.isOpen}
        onClose={deleteModelDisclosure.onClose}
        model={modelForDeletion}
        hasActiveDeployments={hasActiveDeployments}
        loading={deleteModelMutation.isPending}
        onConfirmAction={({ name }: { name: string }) => {
          deleteModelMutation.mutate({
            name,
            force: hasActiveDeployments,
          });
        }}
      />

      <DeleteWorkloadModal
        isOpen={deleteWorkloadDisclosure.isOpen}
        onOpenChange={deleteWorkloadDisclosure.onOpenChange}
        workload={workloadForDeletion}
        onConfirmAction={(id: string) => {
          deleteWorkloadMutation.mutate(id);
        }}
      />

      {modelForAIMDeploy && activeProject && (
        <DeployCustomAIMDrawer
          model={modelForAIMDeploy}
          namespace={activeProject}
          sourceUri={modelForAIMDeploy.sourceUri}
          isOpen={true}
          onClose={() => setModelForAIMDeploy(null)}
        />
      )}

      {finetuneDisclosure.isOpen && activeProject ? (
        <FinetuneWizard
          onClose={finetuneDisclosure.onClose}
          model={modelToFinetune}
          finetunableModels={finetunableModels ?? []}
          onConfirmAction={async ({
            id,
            params,
          }: {
            id: string;
            params: ModelFinetuneParams;
          }) => {
            try {
              await finetuneModelMutation.mutateAsync({ id, params });
            } catch {
              // The mutation's onError handler surfaces the failure to the user.
            }
          }}
        />
      ) : null}
    </div>
  );
};

export default FineTuneModels;
