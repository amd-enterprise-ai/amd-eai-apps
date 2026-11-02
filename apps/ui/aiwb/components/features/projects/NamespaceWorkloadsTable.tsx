// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo, useState } from 'react';

import { useTranslation } from 'next-i18next';
import { useRouter } from 'next/router';
import { fetchProjectWorkloadMetrics } from '@/lib/app/projects';
import type { FetchProjectWorkloadMetricsParams } from '@/lib/app/projects';
import {
  aimParser,
  getMaxSupportedLoraRank,
  getModelCapability,
  resolveAIMServiceDisplay,
} from '@/lib/app/aims';
import {
  deleteInferenceDeployment,
  listAllInferenceDeployments,
} from '@/lib/app/inference';
import { useInferenceModelsByName } from '@/hooks/useInferenceModelsByName';
import { deleteWorkspace } from '@/lib/app/workloads';
import {
  cancelFineTuningJob,
  listAllProjectFineTunedModels,
} from '@/lib/app/models';
import { useProfileSpecsForServices } from '@/hooks/useProfileSpecsForServices';
import { useCustomProfileDeployments } from '@/hooks/useCustomProfileDeployments';
import { resolveModelDeploymentName } from '@/lib/app/modelDeploymentDisplay';
import {
  AIMService,
  FINE_TUNED_LABEL,
  NAMESPACE_AIM_MODEL_LABEL,
} from '@/types/aims';

import { displayMegabytesInGigabytes } from '@amdenterpriseai/utils/app';
import { getWorkloadStatusVariants } from '@/utils/workloads';
import { getWorkloadTypeVariants } from '@amdenterpriseai/utils/app';

import { TableColumns } from '@amdenterpriseai/types';
import { SortDirection } from '@amdenterpriseai/types';
import type { EnrichedWorkloadMetrics } from '@/types/projects';
import {
  useDebouncedCallback,
  useOverlayState,
  useSystemToast,
} from '@amdenterpriseai/hooks';
import { CollectionRequestParams } from '@amdenterpriseai/types';

import {
  ChipDisplay,
  DateDisplay,
  NoDataDisplay,
  ServerSideDataTable,
  StatusDisplay,
} from '@amdenterpriseai/components';
import { ActionItem } from '@amdenterpriseai/types';

import {
  IconEye,
  IconFileText,
  IconLink,
  IconMessage,
  IconTrash,
} from '@tabler/icons-react';

import {
  ModelProfileSummary,
  toProfileSummaryFields,
} from '@/components/shared/ModelProfileSummary';
import DeleteWorkloadModal from '@/components/features/workloads/DeleteWorkloadModal';
import WorkloadLogsModal from '@/components/features/workloads/WorkloadLogsModal';
import AIMConnectModal from '@/components/features/models/AIMConnectModal';
import { useProject } from '@/contexts/ProjectContext';
import { SUBMITTER_ANNOTATION_KEY } from '@/components/features/secrets/constants';

interface Props {
  namespace: string;
}

type NamespaceWorkloadsTableField =
  | 'displayName'
  | 'type'
  | 'status'
  | 'gpuCount'
  | 'vram'
  | 'createdAt'
  | 'createdBy';

const columns: TableColumns<NamespaceWorkloadsTableField | null> = [
  {
    key: 'displayName',
    sortable: true,
  },
  {
    key: 'type',
    sortable: true,
  },
  { key: 'status', sortable: true },
  { key: 'gpuCount' },
  { key: 'vram' },
  { key: 'createdAt', sortable: true },
  { key: 'createdBy', sortable: true },
];

const API_REQUEST_DEFAULTS: CollectionRequestParams<EnrichedWorkloadMetrics> = {
  page: 1,
  pageSize: 20,
  sort: [
    {
      field: 'createdAt' as keyof EnrichedWorkloadMetrics,
      direction: SortDirection.DESC,
    },
  ],
  filter: [],
};

export const NamespaceWorkloadsTable: React.FC<Props> = ({ namespace }) => {
  const { t } = useTranslation(['projects', 'workloads', 'common']);
  const { t: tModels } = useTranslation('models');
  const { t: workloadsT } = useTranslation('workloads');
  const router = useRouter();
  const { projectPath, projectUrl } = useProject();
  const { toast } = useSystemToast();
  const queryClient = useQueryClient();

  const [tableParams, setTableParams] =
    useState<CollectionRequestParams<EnrichedWorkloadMetrics>>(
      API_REQUEST_DEFAULTS,
    );
  const [workloadBeingSelected, setWorkloadBeingSelected] = useState<
    EnrichedWorkloadMetrics | undefined
  >(undefined);
  const [resourceForConnect, setResourceForConnect] = useState<
    EnrichedWorkloadMetrics | undefined
  >(undefined);

  const {
    isOpen: isDeleteWorkloadModalOpen,
    onOpen: onDeleteWorkloadModalOpen,
    onOpenChange: onDeleteWorkloadModalOpenChange,
  } = useOverlayState();

  const {
    isOpen: isWorkloadLogsModalOpen,
    onOpen: onWorkloadLogsModalOpen,
    onOpenChange: onWorkloadLogsModalOpenChange,
  } = useOverlayState();

  const {
    isOpen: isConnectModalOpen,
    onOpen: onConnectModalOpen,
    onClose: onConnectModalClose,
  } = useOverlayState();

  const fetchParams = useMemo<FetchProjectWorkloadMetricsParams>(() => {
    const sortField = tableParams.sort?.[0]?.field as string | undefined;
    const sortDirection = tableParams.sort?.[0]?.direction;

    return {
      page: tableParams.page,
      pageSize: tableParams.pageSize,
      sortBy: sortField,
      sortOrder:
        sortDirection === undefined
          ? undefined
          : sortDirection === 'ascending'
            ? 'asc'
            : 'desc',
    };
  }, [tableParams]);

  const { data: namespaceMetrics, isFetching: isNamespaceMetricsLoading } =
    useQuery({
      queryKey: ['namespace', namespace, 'workloads', fetchParams],
      queryFn: () => fetchProjectWorkloadMetrics(namespace, fetchParams),
      enabled: !!namespace,
    });

  const { data: aimServices, isFetching: isAimServicesLoading } = useQuery({
    queryKey: ['namespace', namespace, 'aim-services'],
    queryFn: () => listAllInferenceDeployments(namespace),
    enabled: !!namespace,
  });

  // Cluster-catalog models are only needed to enrich the display for cluster-scoped AIM
  // services. Namespace-scoped AIMModel services (fine-tuned and custom-imported) aren't
  // in that catalog — resolveAIMServiceDisplay already falls back to their annotations,
  // so we skip those names.
  const clusterAimNames = useMemo(
    () =>
      (aimServices ?? [])
        .filter(
          (s) =>
            s.metadata.labels?.[FINE_TUNED_LABEL] !== 'true' &&
            s.metadata.labels?.[NAMESPACE_AIM_MODEL_LABEL] !== 'true',
        )
        .map((s) => s.spec?.model?.name)
        .filter((name): name is string => !!name),
    [aimServices],
  );
  const { byName: clusterAimsByName, isLoading: isParsedAIMsLoading } =
    useInferenceModelsByName(clusterAimNames);
  const parsedAIMs = useMemo(
    () => Array.from(clusterAimsByName.values()).map((m) => aimParser(m)),
    [clusterAimsByName],
  );

  // Fine-tuned AIMModels in the project — needed so we can derive their
  // status.aimId and fetch only the namespace AIMProfiles actually
  // referenced by displayed FT services.
  const { data: fineTunedModels = [], isLoading: isFineTunedLoading } =
    useQuery({
      queryKey: ['project', namespace, 'fine-tuned-models'],
      queryFn: () => listAllProjectFineTunedModels(namespace),
      enabled: !!namespace,
      staleTime: 5 * 60_000,
    });

  // Profile lookup map built from per-aimId fetches against the cluster
  // and project profile endpoints. Wait for both upstream model fetches to
  // settle before deriving aimIds — otherwise each per-name model landing
  // would trigger a superseding profile fetch.
  const isUpstreamLoading = isParsedAIMsLoading || isFineTunedLoading;
  const aimIds = isUpstreamLoading
    ? []
    : [
        ...Array.from(clusterAimsByName.values()).map((m) => m.status?.aimId),
        ...fineTunedModels.map((m) => m.status?.aimId),
      ].filter((id): id is string => !!id);
  const resolvedProfiles = useMemo(
    () => aimServices?.map(({ status }) => status?.resolvedProfile) ?? [],
    [aimServices],
  );
  const { specByName: profileSpecByName } = useProfileSpecsForServices({
    aimIds,
    project: namespace,
    resolvedProfiles,
  });
  const { profileByServiceId: customProfileByServiceId } =
    useCustomProfileDeployments({
      services: aimServices ?? [],
      project: namespace,
    });

  // Merge resolved profile spec into table rows so HeroUI's TableBody sees a
  // new array reference when AIM services arrive and rows can render
  // hardware details.
  const tableData = useMemo((): EnrichedWorkloadMetrics[] => {
    const rows = namespaceMetrics?.data ?? [];
    if (!aimServices || aimServices.length === 0) return rows;

    // TODO: This is workaround as the API doesn't return createdAt and createdBy as it still reading from DB.

    const aimServiceById = new Map<string, AIMService>(
      aimServices.flatMap((s) => (s.id ? [[s.id, s]] : [])),
    );

    return rows.map((item) => {
      const aimService = aimServiceById.get(String(item.id));
      if (!aimService) return item;
      const customProfile = customProfileByServiceId.get(String(item.id));
      const baseProfile =
        customProfile?.profile ??
        toProfileSummaryFields(aimService, profileSpecByName);
      // Custom-profile axes never carry maxLoraRank — it's sourced from the
      // deployment's own spec, not the profile — so fold it in explicitly
      // rather than letting a custom profile short-circuit past it.
      const maxLoraRank =
        baseProfile?.maxLoraRank ?? getMaxSupportedLoraRank(aimService.spec);

      return {
        ...item,
        createdAt:
          item.createdAt ?? aimService?.metadata?.creationTimestamp ?? null,
        createdBy:
          item.createdBy ??
          aimService?.metadata?.annotations?.[SUBMITTER_ANNOTATION_KEY] ??
          null,
        metric: baseProfile?.metric ?? null,
        gpu: baseProfile?.gpu ?? null,
        templateGpuCount: baseProfile?.templateGpuCount ?? null,
        acceleratorType: baseProfile?.acceleratorType ?? null,
        precision: baseProfile?.precision ?? null,
        maxLoraRank: maxLoraRank ?? null,
        profileDisplayName: customProfile?.displayName ?? null,
      };
    });
  }, [
    namespaceMetrics?.data,
    aimServices,
    profileSpecByName,
    customProfileByServiceId,
  ]);

  const connectInfo = useMemo(() => {
    if (
      !resourceForConnect ||
      resourceForConnect.resourceType !== 'AIMService' ||
      !aimServices
    )
      return undefined;
    const service = aimServices.find((s) => s.id === resourceForConnect.id);
    if (!service) return undefined;
    const modelName = service.status?.resolvedModel?.name ?? undefined;
    return {
      serviceId: service.id ?? undefined,
      endpoints: service.endpoints,
      modelName,
      capability: getModelCapability(
        resolveAIMServiceDisplay(service, parsedAIMs).tags,
      ),
    };
  }, [resourceForConnect, aimServices, parsedAIMs]);

  const { mutate: deleteWorkloadMutated } = useMutation({
    mutationFn: (id: string) => {
      const resource = workloadBeingSelected;
      if (!resource) {
        throw new Error('No resource selected');
      }

      if (resource.resourceType === 'AIMService') {
        return deleteInferenceDeployment(namespace, id);
      } else if (resource.type === 'FINE_TUNING') {
        return cancelFineTuningJob(id, namespace);
      } else if (resource.type === 'WORKSPACE') {
        return deleteWorkspace(namespace, id);
      }
      // Generic /workloads DELETE was removed, so deletion is capability-specific.
      throw new Error(
        `No delete capability for workload type ${resource.type}`,
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ['namespace', namespace, 'workloads'],
      });
      queryClient.invalidateQueries({
        queryKey: ['namespace', namespace, 'stats'],
      });
      toast.success(t('workloads:list.actions.delete.notification.success'));
    },
    onError: (_) => {
      toast.error(t('workloads:list.actions.delete.notification.error'));
    },
  });

  const rowActions = useMemo(
    () => (item: EnrichedWorkloadMetrics) => {
      const actionsList: ActionItem<EnrichedWorkloadMetrics>[] = [];

      actionsList.push({
        key: 'details',
        label: t('workloads:list.actions.details.label'),
        startContent: <IconEye />,
        onPress: (w: EnrichedWorkloadMetrics) => {
          const pathname =
            w.resourceType === 'AIMService'
              ? projectPath(`/aims/${w.id}`)
              : projectPath(`/workloads/${w.id}`);

          router.push({
            pathname,
            query: { ref: router.asPath },
          });
        },
      });

      if (item.type === 'INFERENCE' && item.status === 'Running') {
        const service =
          item.resourceType === 'AIMService'
            ? aimServices?.find((s) => s.id === item.id)
            : undefined;
        const capability = service
          ? getModelCapability(
              resolveAIMServiceDisplay(service, parsedAIMs).tags,
            )
          : 'chat';
        // Transcription deployments have no chat surface; omit the chat action.
        if (capability !== 'transcription') {
          actionsList.push({
            key: 'chat',
            label: t('workloads:list.actions.chat.label'),
            startContent: <IconMessage />,
            onPress: () => {
              window.open(projectUrl(`/chat?workload=${item.id}`), '_blank');
            },
          });
        }
        if (item.resourceType === 'AIMService') {
          actionsList.push({
            key: 'connect',
            label: tModels('aimCatalog.actions.connect.label'),
            startContent: <IconLink />,
            onPress: (w: EnrichedWorkloadMetrics) => {
              setResourceForConnect(w);
              onConnectModalOpen();
            },
          });
        }
      }

      actionsList.push({
        key: 'logs',
        label: t('workloads:list.actions.logs.label'),
        startContent: <IconFileText />,
        onPress: (w: EnrichedWorkloadMetrics) => {
          setWorkloadBeingSelected(w);
          onWorkloadLogsModalOpen();
        },
      });

      // The delete mutation can only dispatch to capability-specific endpoints
      // (AIM service / fine-tuning / workspace). Any other row type has no owning
      // capability surface, so the action is filtered out rather than letting the
      // user click into a thrown error.
      const canDelete =
        item.status !== 'Deleted' &&
        (item.resourceType === 'AIMService' ||
          item.type === 'FINE_TUNING' ||
          item.type === 'WORKSPACE');

      if (canDelete) {
        actionsList.push({
          key: 'delete',
          label: t('workloads:list.actions.delete.label'),
          color: 'danger',
          startContent: <IconTrash />,
          onPress: (w: EnrichedWorkloadMetrics) => {
            setWorkloadBeingSelected(w);
            onDeleteWorkloadModalOpen();
          },
        });
      }

      return actionsList;
    },
    [
      t,
      router,
      onWorkloadLogsModalOpen,
      onDeleteWorkloadModalOpen,
      onConnectModalOpen,
      aimServices,
      parsedAIMs,
    ],
  );

  const handleTableParamsChange = useDebouncedCallback(
    (params: CollectionRequestParams<EnrichedWorkloadMetrics>) => {
      setTableParams(params);
    },
    100,
  );

  const customRenderers: Partial<
    Record<
      NamespaceWorkloadsTableField,
      (item: EnrichedWorkloadMetrics) => React.ReactNode | string
    >
  > = {
    vram: (item) =>
      item.vram != null ? (
        displayMegabytesInGigabytes(item.vram)
      ) : (
        <NoDataDisplay />
      ),
    createdAt: (item) => {
      if (item.createdAt) {
        return <DateDisplay date={item.createdAt} />;
      }
      return <NoDataDisplay />;
    },
    displayName: (item) => {
      const isAimService = item.resourceType === 'AIMService';
      const profileSummary = <ModelProfileSummary profile={item} t={tModels} />;

      if (isAimService && aimServices && parsedAIMs.length > 0) {
        const aimService = aimServices.find(
          (service) => service.id === item.id,
        );
        if (aimService) {
          const displayInfo = resolveAIMServiceDisplay(aimService, parsedAIMs);
          const displayName = resolveModelDeploymentName({
            displayName: item.displayName,
            resourceName: item.name,
            canonicalName: displayInfo.canonicalName,
            imageVersion: displayInfo.imageVersion,
          });
          return (
            <div className="flex flex-col gap-1">
              <span>{displayName}</span>
              {profileSummary}
            </div>
          );
        }
      }

      const displayName = item.displayName ?? item.name;
      return (
        <div className="flex flex-col gap-1">
          {displayName ? <span>{displayName}</span> : <NoDataDisplay />}
          {profileSummary}
        </div>
      );
    },
    status: (item) => (
      <StatusDisplay
        type={item.status}
        variants={getWorkloadStatusVariants(workloadsT)}
      />
    ),
    type: (item) => (
      <ChipDisplay
        type={item.type ?? t('common:error.misc.unknownEntity')}
        variants={getWorkloadTypeVariants(workloadsT)}
      />
    ),
    gpuCount: (item) => item.gpuCount ?? <NoDataDisplay />,
    createdBy: (item) => item.createdBy ?? <NoDataDisplay />,
  };

  return (
    <div>
      <ServerSideDataTable
        filters={[]}
        handleDataRequest={handleTableParamsChange}
        total={namespaceMetrics?.pagination.total ?? 0}
        data={tableData}
        columns={columns}
        customRenderers={customRenderers}
        defaultSortByField="createdAt"
        defaultSortDirection={SortDirection.DESC}
        rowActions={rowActions}
        translation={t}
        idKey="id"
        translationKeyPrefix="workloads"
        isLoading={
          isNamespaceMetricsLoading ||
          isAimServicesLoading ||
          isParsedAIMsLoading
        }
      />
      <DeleteWorkloadModal
        isOpen={isDeleteWorkloadModalOpen}
        onOpenChange={onDeleteWorkloadModalOpenChange}
        workload={workloadBeingSelected}
        onConfirmAction={deleteWorkloadMutated}
      />
      {isWorkloadLogsModalOpen && workloadBeingSelected && (
        <WorkloadLogsModal
          onOpenChange={onWorkloadLogsModalOpenChange}
          isOpen={isWorkloadLogsModalOpen}
          workload={workloadBeingSelected}
          namespace={namespace}
        />
      )}
      <AIMConnectModal
        isOpen={isConnectModalOpen}
        onOpenChange={(isOpen) => {
          if (!isOpen) {
            onConnectModalClose();
            setResourceForConnect(undefined);
          }
        }}
        serviceId={connectInfo?.serviceId}
        endpoints={connectInfo?.endpoints}
        modelName={connectInfo?.modelName}
        capability={connectInfo?.capability ?? 'chat'}
        onChatRequested={(serviceId) => {
          window.open(projectUrl(`/chat?workload=${serviceId}`), '_blank');
          onConnectModalClose();
          setResourceForConnect(undefined);
        }}
      />
    </div>
  );
};

export default NamespaceWorkloadsTable;
