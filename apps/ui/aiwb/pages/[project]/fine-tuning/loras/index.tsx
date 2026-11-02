// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  ActionButton,
  ActionsToolbar,
  Alert,
  ClientSideDataTable,
  DateDisplay,
  NoDataDisplay,
  StatusDisplay,
  Tooltip,
} from '@amdenterpriseai/components';
import { useOverlayState, useSystemToast } from '@amdenterpriseai/hooks';
import {
  type ActionItem,
  type ClientSideDataFilter,
  FilterComponentType,
  type FilterValueMap,
  SortDirection,
  type TableColumns,
} from '@amdenterpriseai/types';
import { APIRequestError, getFilteredData } from '@amdenterpriseai/utils/app';
import {
  IconAffiliate,
  IconCpu,
  IconEye,
  IconLink,
  IconSquareRotatedAsterisk,
  IconTrash,
} from '@tabler/icons-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { GetServerSidePropsContext } from 'next';
import { useEffect, useMemo, useRef, useState } from 'react';

import { useTranslation } from 'next-i18next';

import { getPageTranslations } from '@/lib/server/i18n';

import { AttachLoraModal } from '@/components/features/loras/AttachLoraModal';
import { DeleteLoraModal } from '@/components/features/loras/DeleteLoraModal';
import { LoraDetailsModal } from '@/components/features/loras/LoraDetailsModal';
import { FinetuneWizard } from '@/components/features/models/FinetuneWizard';
import { TruncatedDescription } from '@/components/shared/TruncatedDescription';
import DeleteWorkloadModal from '@/components/features/workloads/DeleteWorkloadModal';
import { useProject } from '@/contexts/ProjectContext';
import { buildPageBreadcrumb } from '@/lib/app/breadcrumbs';
import {
  deleteAdapterArtifact,
  listAllAdapterArtifacts,
  waitForAdapterArtifactRemoval,
} from '@/lib/app/artifacts';
import { listInferenceDeployments } from '@/lib/app/inference';
import {
  cancelFineTuningJob,
  finetuneModel,
  getFinetunableModels,
} from '@/lib/app/models';
import { fetchAllPages } from '@/lib/app/pagination';
import { listAllWorkloads } from '@/lib/app/workloads';
import { AIM_MODEL_TRAINING_OUTPUT_ANNOTATION } from '@/types/aims';
import type { AIMService } from '@/types/aims';
import type { components } from '@/types/api';
import type { LoraAdapter } from '@/types/artifacts';
import type { FinetunableModel, ModelFinetuneParams } from '@/types/models';
import type { ResourceStatus, Workload } from '@/types/workloads';
import { getWorkloadStatusVariants } from '@/utils/workloads';

const LoraTableField = {
  NAME: 'displayName',
  STATUS: 'status',
  DEPLOYMENTS: 'deploymentCount',
  CREATED_AT: 'createdAt',
  CREATED_BY: 'createdBy',
} as const;

type LoraTableField = (typeof LoraTableField)[keyof typeof LoraTableField];
type WorkloadResponse = components['schemas']['WorkloadResponse'];
type LoraRow =
  | (Omit<LoraAdapter, 'status'> & {
      deploymentCount: number;
      source: 'artifact';
      status: ResourceStatus;
    })
  | {
      id: string;
      name: string;
      displayName: string;
      description?: string;
      compatibleWith: string[];
      createdAt: string;
      createdBy?: string;
      source: 'workload';
      status: components['schemas']['WorkloadStatus'];
    };

const convertFilterValueMap = (
  filterValues: FilterValueMap,
): ClientSideDataFilter<LoraRow>[] => {
  const filters: ClientSideDataFilter<LoraRow>[] = [];
  if (filterValues.search?.length) {
    filters.push({
      compositeFields: [
        { field: 'displayName' },
        { field: 'name' },
        { field: 'description' },
        { field: 'compatibleWith' },
      ],
      values: filterValues.search,
    });
  }
  if (filterValues.baseModels?.length) {
    filters.push({
      field: 'compatibleWith',
      values: filterValues.baseModels,
      exact: true,
    });
  }
  return filters;
};

const LorasPage = () => {
  const { t } = useTranslation('loras');
  const { t: tModels } = useTranslation('models');
  const { t: tWorkloads } = useTranslation('workloads');
  const queryClient = useQueryClient();
  const { toast } = useSystemToast();
  const { activeProject } = useProject();
  const deleteDisclosure = useOverlayState();
  const deleteWorkloadDisclosure = useOverlayState();
  const detailsDisclosure = useOverlayState();
  const attachDisclosure = useOverlayState();
  const finetuneDisclosure = useOverlayState();
  const [adapterForDeletion, setAdapterForDeletion] = useState<LoraAdapter>();
  const [workloadForDeletion, setWorkloadForDeletion] =
    useState<Pick<Workload, 'id' | 'displayName'>>();
  const [adapterForDetails, setAdapterForDetails] = useState<string>();
  const [adapterForAttach, setAdapterForAttach] = useState<LoraAdapter>();
  const [filters, setFilters] = useState<ClientSideDataFilter<LoraRow>[]>([]);
  const {
    data: adapters = [],
    isLoading: areAdaptersLoading,
    isFetching: areAdaptersFetching,
    refetch: refetchAdapters,
    error: adaptersError,
    dataUpdatedAt: adaptersUpdatedAt,
  } = useQuery({
    queryKey: ['project', activeProject, 'artifacts'],
    queryFn: () => listAllAdapterArtifacts(activeProject!),
    enabled: !!activeProject,
  });
  const {
    data: workloads = [],
    isLoading: areWorkloadsLoading,
    isFetching: areWorkloadsFetching,
    refetch: refetchWorkloads,
    error: workloadsError,
    dataUpdatedAt: workloadsUpdatedAt,
  } = useQuery({
    queryKey: ['project', activeProject, 'workloads', 'lora-fine-tuning-jobs'],
    queryFn: () =>
      listAllWorkloads(activeProject!, {
        workloadType: ['FINE_TUNING'],
        // Completed jobs are excluded: they register as adapter artifacts, which
        // are listed separately, so including them here would double-list them.
        // Failed jobs have no artifact, so surface them here for investigation.
        statusFilter: ['Pending', 'Starting', 'Running', 'Failed'],
      }),
    refetchInterval: 30000,
    enabled: !!activeProject,
  });
  const { data: finetunableModels = [] } = useQuery<FinetunableModel[]>({
    queryKey: ['models', 'finetunable'],
    queryFn: getFinetunableModels,
  });
  const {
    data: deployments,
    isLoading: isDeploymentsLoading,
    isFetching: isDeploymentsFetching,
    isError: isDeploymentsError,
    error: deploymentsError,
    refetch: refetchDeployments,
    dataUpdatedAt: deploymentsUpdatedAt,
  } = useQuery({
    // Walks pages directly (rather than the listAllX wrapper) so a fetch
    // failure surfaces as a query error instead of silently resolving to [].
    // The deletion guard below depends on being able to tell "no usage" apart
    // from "usage unknown".
    queryKey: ['project', activeProject, 'inference', 'all'],
    queryFn: () =>
      fetchAllPages<AIMService>((page, pageSize) =>
        listInferenceDeployments(activeProject!, { page, pageSize }),
      ),
    enabled: !!activeProject,
  });
  const deploymentCountByAdapter = useMemo(() => {
    const counts = new Map<string, number>();
    // Counts every referencing deployment regardless of status (and of
    // whether its base model is a cluster catalog entry or a project-scoped
    // fine-tuned/custom model) so it matches the backend's deletion guard,
    // which blocks removal for any reference, not just Running ones.
    for (const deployment of deployments ?? []) {
      const adapterNames = new Set(
        deployment.spec?.adapters?.map(({ name }) => name),
      );
      adapterNames.forEach((name) => {
        counts.set(name, (counts.get(name) ?? 0) + 1);
      });
    }
    return counts;
  }, [deployments]);
  const loras = useMemo<LoraRow[]>(
    () => [
      ...workloads
        .filter(
          (workload: WorkloadResponse) =>
            workload.annotations?.[AIM_MODEL_TRAINING_OUTPUT_ANNOTATION] ===
            'lora',
        )
        .map(
          (workload: WorkloadResponse): LoraRow => ({
            id: workload.id,
            name: workload.name,
            displayName: workload.displayName || workload.name,
            compatibleWith: [],
            createdAt: workload.createdAt,
            createdBy: workload.createdBy ?? undefined,
            source: 'workload',
            status: workload.status,
          }),
        ),
      ...adapters.map(
        (adapter): LoraRow => ({
          ...adapter,
          deploymentCount: deploymentCountByAdapter.get(adapter.name) ?? 0,
          source: 'artifact',
          status:
            adapter.readiness === 'Ready'
              ? 'Complete'
              : adapter.readiness === 'NotReady'
                ? 'Pending'
                : 'Unknown',
        }),
      ),
    ],
    [adapters, deploymentCountByAdapter, workloads],
  );
  const loraWorkloadIds = useMemo(
    () =>
      new Set(
        workloads
          .filter(
            (workload: WorkloadResponse) =>
              workload.annotations?.[AIM_MODEL_TRAINING_OUTPUT_ANNOTATION] ===
              'lora',
          )
          .map((workload) => workload.id),
      ),
    [workloads],
  );
  const previousLoraWorkloadIdsRef = useRef<Set<string>>(new Set());
  useEffect(() => {
    const hasTransitionedOut = Array.from(
      previousLoraWorkloadIdsRef.current,
    ).some((id) => !loraWorkloadIds.has(id));
    if (hasTransitionedOut) {
      // A LoRA fine-tuning job dropped out of the tracked list because it
      // completed (registering a new adapter) or was canceled. Failed jobs stay
      // listed, so they don't trigger this. The artifact query has no polling
      // interval, so nudge it to refresh rather than leave a newly-registered
      // adapter missing until the user manually refreshes.
      refetchAdapters();
    }
    previousLoraWorkloadIdsRef.current = loraWorkloadIds;
  }, [loraWorkloadIds, refetchAdapters]);
  const filteredLoras = useMemo(
    () => getFilteredData(loras, filters),
    [filters, loras],
  );
  const baseModelOptions = useMemo(
    () =>
      Array.from(
        new Set(adapters.flatMap(({ compatibleWith }) => compatibleWith)),
      )
        .sort()
        .map((model) => ({ key: model, label: model })),
    [adapters],
  );
  const filterConfig = useMemo(
    () => ({
      search: {
        name: 'search',
        label: t('list.filters.search.placeholder'),
        placeholder: t('list.filters.search.placeholder'),
        type: FilterComponentType.TEXT,
      },
      baseModels: {
        name: 'baseModels',
        label: t('list.filters.baseModels.label'),
        placeholder: t('list.filters.baseModels.placeholder'),
        type: FilterComponentType.DROPDOWN,
        fields: baseModelOptions,
      },
    }),
    [baseModelOptions, t],
  );
  useEffect(() => {
    if (adaptersError) {
      toast.error(
        t('notifications.refresh.adaptersError', {
          error: String(adaptersError.message),
        }),
      );
    }
  }, [adaptersError, toast, t]);
  useEffect(() => {
    if (workloadsError) {
      toast.error(
        t('notifications.refresh.workloadsError', {
          error: String(workloadsError.message),
        }),
      );
    }
  }, [workloadsError, toast, t]);
  useEffect(() => {
    if (deploymentsError) {
      toast.error(
        t('notifications.refresh.deploymentsError', {
          error: String(deploymentsError.message),
        }),
      );
    }
  }, [deploymentsError, toast, t]);
  const hasLoadError = Boolean(
    adaptersError || workloadsError || deploymentsError,
  );
  const closeDeleteModal = () => {
    deleteDisclosure.onClose();
    setAdapterForDeletion(undefined);
  };
  const deleteMutation = useMutation({
    mutationFn: (name: string) => deleteAdapterArtifact(activeProject!, name),
    onSuccess: async (_data, name) => {
      toast.success(t('actions.delete.notification.success'));
      closeDeleteModal();
      // The delete endpoint returns 202 once removal is accepted, not once it's
      // finished, so wait for the artifact to actually disappear before
      // refetching the list to avoid a brief flash of the deleted row.
      await waitForAdapterArtifactRemoval(activeProject!, name);
      queryClient.invalidateQueries({
        queryKey: ['project', activeProject, 'artifacts'],
      });
    },
    onError: (error: unknown) => {
      closeDeleteModal();
      toast.error(
        error instanceof APIRequestError
          ? error.message
          : t('actions.delete.notification.error'),
      );
    },
  });
  const cancelWorkloadMutation = useMutation({
    mutationFn: (id: string) => cancelFineTuningJob(id, activeProject!),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ['project', activeProject, 'workloads'],
      });
      toast.success(t('actions.delete.workloadNotification.success'));
      deleteWorkloadDisclosure.onClose();
    },
    onError: (error: unknown) => {
      toast.error(
        error instanceof APIRequestError
          ? error.message
          : t('actions.delete.workloadNotification.error'),
      );
    },
  });
  const finetuneMutation = useMutation({
    mutationFn: ({ id, params }: { id: string; params: ModelFinetuneParams }) =>
      finetuneModel(id, params, activeProject!),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ['project', activeProject, 'models'],
      });
      queryClient.invalidateQueries({
        queryKey: ['project', activeProject, 'workloads'],
      });
      toast.success(tModels('finetuneWizard.notifications.success'));
      finetuneDisclosure.onClose();
    },
    onError: () => {
      toast.error(tModels('finetuneWizard.notifications.error'));
    },
  });
  const rowActions = (item: LoraRow): ActionItem<LoraRow>[] => {
    const actions: ActionItem<LoraRow>[] = [];
    if (item.source === 'artifact') {
      actions.push({
        key: 'attach',
        label: t('actions.attach.label'),
        color: 'default',
        startContent: <IconLink />,
        isDisabled: item.status !== 'Complete',
        onPress: () => {
          setAdapterForAttach(item);
          attachDisclosure.onOpen();
        },
      });
      actions.push({
        key: 'details',
        label: t('actions.details'),
        color: 'default',
        startContent: <IconEye />,
        onPress: () => {
          setAdapterForDetails(item.name);
          detailsDisclosure.onOpen();
        },
      });
    }
    actions.push({
      key: 'delete',
      label: t('actions.delete.label'),
      color: 'danger',
      startContent: <IconTrash />,
      // Fail closed: while deployment usage is loading, refetching, or failed
      // to load, usage is unknown rather than zero, so deletion stays disabled
      // instead of letting a stale/absent count enable a backend-rejected delete.
      isDisabled:
        item.source === 'artifact' &&
        (isDeploymentsLoading ||
          isDeploymentsFetching ||
          isDeploymentsError ||
          item.deploymentCount > 0),
      onPress: () => {
        if (item.source === 'artifact') {
          setAdapterForDeletion(item);
          deleteDisclosure.onOpen();
          return;
        }
        setWorkloadForDeletion({
          id: item.id,
          displayName: item.displayName,
        });
        deleteWorkloadDisclosure.onOpen();
      },
    });
    return actions;
  };
  const workloadStatusVariants = useMemo(
    () => getWorkloadStatusVariants(tWorkloads),
    [tWorkloads],
  );
  const columns: TableColumns<LoraTableField | null> = [
    {
      key: LoraTableField.NAME,
      sortable: true,
      className: 'w-full min-w-64 max-w-0',
    },
    {
      key: LoraTableField.STATUS,
      sortable: true,
      className: 'w-0 whitespace-nowrap',
    },
    {
      key: LoraTableField.DEPLOYMENTS,
      sortable: true,
      className: 'w-0 whitespace-nowrap',
    },
    {
      key: LoraTableField.CREATED_AT,
      sortable: true,
      className: 'w-0 whitespace-nowrap',
    },
    {
      key: LoraTableField.CREATED_BY,
      sortable: true,
      className: 'w-0 whitespace-nowrap',
    },
  ];
  const customRenderers: Record<
    LoraTableField,
    (item: LoraRow) => React.ReactNode | string
  > = {
    [LoraTableField.NAME]: (item) => {
      const [primaryBaseModel, ...otherBaseModels] = item.compatibleWith;
      const description =
        item.source === 'artifact' ? item.description?.trim() : undefined;
      const rank = item.source === 'artifact' ? item.rank : null;
      const hasMetadata = primaryBaseModel || rank != null;
      return (
        <div className="flex min-w-0 flex-col gap-1">
          <span>{item.displayName}</span>
          {description ? (
            <TruncatedDescription description={description} />
          ) : null}
          {hasMetadata ? (
            <span className="flex min-w-0 items-center gap-1 text-xs text-muted">
              {primaryBaseModel ? (
                <span className="inline-flex min-w-0 items-center gap-1">
                  <span className="inline-flex shrink-0 items-center gap-0.5">
                    <IconCpu size={14} aria-hidden />
                    {primaryBaseModel}
                  </span>
                  {otherBaseModels.length > 0 ? (
                    <Tooltip
                      content={
                        <div className="flex flex-col gap-1">
                          {otherBaseModels.map((model) => (
                            <span key={model}>{model}</span>
                          ))}
                        </div>
                      }
                    >
                      {/* biome-ignore lint/a11y/useSemanticElements: the element reveals supplemental text rather than performing an action. */}
                      <span
                        className="shrink-0 cursor-help underline decoration-dotted"
                        role="button"
                        tabIndex={0}
                      >
                        {t('list.compatibleWithMoreCount', {
                          count: otherBaseModels.length,
                        })}
                      </span>
                    </Tooltip>
                  ) : null}
                </span>
              ) : null}
              {primaryBaseModel && rank != null ? (
                <span aria-hidden>•</span>
              ) : null}
              {rank != null ? (
                <span className="inline-flex shrink-0 items-center gap-0.5">
                  <IconSquareRotatedAsterisk aria-hidden size={14} />
                  {rank}
                </span>
              ) : null}
            </span>
          ) : null}
        </div>
      );
    },
    [LoraTableField.STATUS]: (item) => (
      <StatusDisplay
        type={item.status as ResourceStatus}
        variants={workloadStatusVariants}
      />
    ),
    [LoraTableField.DEPLOYMENTS]: (item) =>
      item.source === 'artifact' && item.deploymentCount ? (
        item.deploymentCount
      ) : (
        <NoDataDisplay />
      ),
    [LoraTableField.CREATED_AT]: (item) =>
      item.createdAt ? (
        <DateDisplay date={item.createdAt} />
      ) : (
        <NoDataDisplay />
      ),
    [LoraTableField.CREATED_BY]: (item) => item.createdBy ?? <NoDataDisplay />,
  };
  return (
    <div className="min-h-full flex flex-col w-full" data-testid="loras-page">
      <ActionsToolbar
        filterConfig={filterConfig}
        onFilterChange={(filterValues) =>
          setFilters(convertFilterValueMap(filterValues))
        }
        onRefresh={() => {
          if (!activeProject) return;
          refetchAdapters();
          refetchWorkloads();
          refetchDeployments();
        }}
        updatedTimestamp={Math.max(
          adaptersUpdatedAt,
          workloadsUpdatedAt,
          deploymentsUpdatedAt,
        )}
        isRefreshing={
          areAdaptersLoading ||
          areAdaptersFetching ||
          areWorkloadsLoading ||
          areWorkloadsFetching ||
          isDeploymentsLoading ||
          isDeploymentsFetching
        }
        endContent={
          <ActionButton
            primary
            isDisabled={
              areAdaptersLoading || areWorkloadsLoading || isDeploymentsLoading
            }
            onPress={finetuneDisclosure.onOpen}
            icon={<IconAffiliate size={16} stroke={3} />}
            data-testid="loras-finetune"
          >
            {t('actions.finetune.title')}
          </ActionButton>
        }
      />
      {hasLoadError ? (
        <Alert
          status="danger"
          title={t('notifications.refresh.loadErrorTitle')}
          description={t('notifications.refresh.loadErrorDescription')}
          className="mb-4"
        />
      ) : null}
      <ClientSideDataTable
        data={filteredLoras}
        className="flex-1 overflow-y-auto"
        columns={columns}
        defaultSortByField={LoraTableField.CREATED_AT}
        defaultSortDirection={SortDirection.DESC}
        translation={t}
        customRenderers={customRenderers}
        rowActions={rowActions}
        isLoading={
          areAdaptersLoading || areWorkloadsLoading || isDeploymentsLoading
        }
        isFetching={
          areAdaptersFetching || areWorkloadsFetching || isDeploymentsFetching
        }
        idKey="id"
      />
      <DeleteLoraModal
        isOpen={deleteDisclosure.isOpen}
        onClose={closeDeleteModal}
        onConfirmAction={(name) => deleteMutation.mutate(name)}
        adapter={adapterForDeletion}
        loading={deleteMutation.isPending}
      />
      <DeleteWorkloadModal
        isOpen={deleteWorkloadDisclosure.isOpen}
        onOpenChange={deleteWorkloadDisclosure.onOpenChange}
        onConfirmAction={(id) => cancelWorkloadMutation.mutate(id)}
        workload={workloadForDeletion}
      />
      <LoraDetailsModal
        name={adapterForDetails}
        isOpen={detailsDisclosure.isOpen}
        onOpenChange={detailsDisclosure.onOpenChange}
      />
      <AttachLoraModal
        adapter={adapterForAttach}
        isOpen={attachDisclosure.isOpen}
        onOpenChange={attachDisclosure.onOpenChange}
      />
      {finetuneDisclosure.isOpen && activeProject ? (
        <FinetuneWizard
          finetunableModels={finetunableModels}
          onClose={finetuneDisclosure.onClose}
          onConfirmAction={async ({ id, params }) => {
            try {
              await finetuneMutation.mutateAsync({ id, params });
            } catch {
              // The mutation's onError handler surfaces the failure to the user.
            }
          }}
        />
      ) : null}
    </div>
  );
};

export async function getServerSideProps(context: GetServerSidePropsContext) {
  const locale = context.locale ?? 'en';
  const translations = await getPageTranslations(locale, [
    'loras',
    'models',
    'workloads',
  ]);

  return {
    props: {
      ...translations,
      pageBreadcrumb: buildPageBreadcrumb(
        translations,
        locale,
        'fineTuning',
        'loras',
      ),
    },
  };
}

export default LorasPage;
