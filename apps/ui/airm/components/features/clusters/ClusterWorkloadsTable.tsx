// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { IconTrash } from '@tabler/icons-react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';

import { useTranslation } from 'next-i18next';
import router from 'next/router';

import {
  useDebouncedCallback,
  useOverlayState,
  useSystemToast,
} from '@amdenterpriseai/hooks';

import { fetchClusterWorkloadsMetrics } from '@/services/app';
import { getClusterProjects } from '@/services/app';
import { deleteWorkload } from '@/services/app';

import { convertToServerSideFilterParams } from '@amdenterpriseai/utils/app';
import { APIRequestError } from '@amdenterpriseai/utils/app';
import { displayMegabytesInGigabytes } from '@amdenterpriseai/utils/app';
import { displayTimestamp } from '@amdenterpriseai/utils/app';
import {
  getWorkloadStatusFilterItems,
  getWorkloadStatusVariants,
  getWorkloadTypeFilterItems,
} from '@/utils/workloads';
import { getWorkloadTypeVariants } from '@amdenterpriseai/utils/app';

import {
  CollectionRequestParams,
  CustomSortFieldMapperConfig,
  FilterParams,
} from '@amdenterpriseai/types';
import { TableColumns } from '@amdenterpriseai/types';
import { FilterComponentType } from '@amdenterpriseai/types';
import { ClusterWorkloadsTableField } from '@/types/enums/cluster-workloads-table-field';
import { FilterOperator } from '@amdenterpriseai/types';
import { SortDirection } from '@amdenterpriseai/types';
import { WorkloadType } from '@amdenterpriseai/types';
import { WorkloadStatus } from '@/types/enums/workloads';
import { FilterValueMap } from '@amdenterpriseai/types';
import { ProjectBasicInfo } from '@/types/projects';
import {
  WorkloadWithMetrics,
  ClusterWorkloadsMetricsResponse,
} from '@/types/workloads';

import DeleteWorkloadModal from '@/components/features/workloads/DeleteWorkloadModal';
import {
  ActionsToolbar,
  ChipDisplay,
  ServerSideDataTable,
  StatusDisplay,
} from '@amdenterpriseai/components';

interface Props {
  clusterId: string;
}

const columns: TableColumns<ClusterWorkloadsTableField | null> = [
  {
    key: ClusterWorkloadsTableField.NAME,
    sortable: true,
  },
  {
    key: ClusterWorkloadsTableField.TYPE,
    sortable: true,
  },
  { key: ClusterWorkloadsTableField.STATUS, sortable: true },
  { key: ClusterWorkloadsTableField.GPUS },
  { key: ClusterWorkloadsTableField.VRAM },
  { key: ClusterWorkloadsTableField.CREATED_AT, sortable: true },
  { key: ClusterWorkloadsTableField.PROJECT },
  { key: ClusterWorkloadsTableField.CREATED_BY, sortable: true },
];

const defaultTypeSet = Object.values(WorkloadType);
const defaultStatusSet = Object.values(WorkloadStatus).filter(
  (status) => status !== WorkloadStatus.DELETED,
);

const defaultFilterValues: FilterParams<WorkloadWithMetrics>[] = [
  {
    fields: ['type'],
    operator: FilterOperator.EQ,
    values: defaultTypeSet,
  },
  {
    fields: ['status'],
    operator: FilterOperator.EQ,
    values: defaultStatusSet,
  },
];

const WORKLOADS_METRICS_QUERY_KEY = 'cluster';
const API_REQUEST_DEFAULTS: CollectionRequestParams<WorkloadWithMetrics> = {
  page: 1,
  pageSize: 10,
  sort: [
    {
      field: 'createdAt' as keyof WorkloadWithMetrics,
      direction: SortDirection.DESC,
    },
  ],
  filter: defaultFilterValues,
};

export const ClusterWorkloadsTable: React.FC<Props> = ({ clusterId }) => {
  const { t } = useTranslation('clusters');
  const { t: workloadsT } = useTranslation('workloads');
  const queryClient = useQueryClient();
  const { toast } = useSystemToast();

  const [workloadSelected, setWorkloadSelected] = useState<
    WorkloadWithMetrics | undefined
  >();

  const [filters, setFilters] =
    useState<Array<FilterParams<WorkloadWithMetrics>>>(defaultFilterValues);

  const {
    isOpen: isDeleteWorkloadModalOpen,
    onOpen: onDeleteWorkloadModalOpen,
    onOpenChange,
  } = useOverlayState();

  const { mutate: deleteWorkloadMutation } = useMutation({
    mutationFn: deleteWorkload,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cluster', 'workloads'] });
      queryClient.invalidateQueries({
        queryKey: ['cluster', 'metrics', 'statuses'],
      });
      toast.success(t('list.workloads.actions.delete.notification.success'));
    },
    onError: (error) => {
      toast.error(
        t('list.workloads.actions.delete.notification.error'),
        error as APIRequestError,
      );
    },
  });

  const [workloadsTableParams, setWorkloadsTableParams] =
    useState<CollectionRequestParams<WorkloadWithMetrics>>(
      API_REQUEST_DEFAULTS,
    );

  const {
    data: clusterWorkloadsMetrics,
    isFetching: isClusterWorkloadsMetricsLoading,
    refetch: refetchClusterWorkloadsMetrics,
    dataUpdatedAt: clusterWorkloadsMetricsUpdatedAt,
  } = useQuery<ClusterWorkloadsMetricsResponse>({
    queryKey: [
      WORKLOADS_METRICS_QUERY_KEY,
      clusterId,
      'workloads-metrics',
      workloadsTableParams,
    ],
    queryFn: () =>
      fetchClusterWorkloadsMetrics(clusterId, workloadsTableParams),
  });

  const { data: clusterProjects } = useQuery({
    queryKey: ['cluster', clusterId, 'projects'],
    queryFn: () => getClusterProjects(clusterId),
  });

  const handleWorkloadsTableParamsChange = useDebouncedCallback(
    (params: CollectionRequestParams<WorkloadWithMetrics>) => {
      setWorkloadsTableParams(params);
    },
    100,
  );

  // Merge workloads with project data
  const workloadsWithProjects = useMemo(() => {
    if (!clusterWorkloadsMetrics?.data || !clusterProjects?.data) {
      return clusterWorkloadsMetrics?.data ?? [];
    }

    const projectsMap = new Map(
      clusterProjects.data.map((proj: ProjectBasicInfo) => [proj.id, proj]),
    );

    return clusterWorkloadsMetrics.data.map((workload) => ({
      ...workload,
      project: projectsMap.get(workload.projectId),
    }));
  }, [clusterWorkloadsMetrics, clusterProjects]);

  type WorkloadWithProject = WorkloadWithMetrics & {
    project?: ProjectBasicInfo;
  };

  const customRenderers: Partial<
    Record<
      ClusterWorkloadsTableField,
      (item: WorkloadWithProject) => React.ReactNode | string
    >
  > = {
    [ClusterWorkloadsTableField.VRAM]: (item) =>
      displayMegabytesInGigabytes(item.vram),
    [ClusterWorkloadsTableField.CREATED_AT]: (item) => {
      if (item.createdAt) {
        return displayTimestamp(new Date(item.createdAt));
      }
      return '-';
    },
    [ClusterWorkloadsTableField.PROJECT]: (item) =>
      item.project ? item.project.name : '-',
    [ClusterWorkloadsTableField.STATUS]: (item) => (
      <StatusDisplay
        type={item.status}
        variants={getWorkloadStatusVariants(workloadsT)}
      />
    ),
    [ClusterWorkloadsTableField.TYPE]: (item) => (
      <ChipDisplay
        type={item.type ?? t(`common:error.misc.unknownEntity`)}
        variants={getWorkloadTypeVariants(workloadsT)}
      />
    ),
  };

  const sortFieldMapper: CustomSortFieldMapperConfig<
    WorkloadWithMetrics,
    ClusterWorkloadsTableField
  > = {
    [ClusterWorkloadsTableField.CREATED_AT]: { fields: ['createdAt'] },
    [ClusterWorkloadsTableField.NAME]: { fields: ['displayName'] },
    [ClusterWorkloadsTableField.CREATED_BY]: { fields: ['createdBy'] },
    [ClusterWorkloadsTableField.TYPE]: { fields: ['type'] },
    [ClusterWorkloadsTableField.STATUS]: { fields: ['status'] },
  };

  const rowActions = (item: WorkloadWithProject) => {
    const canBeDeleted = ![
      WorkloadStatus.DELETED,
      WorkloadStatus.DELETING,
    ].includes(item.status);

    const actions = [];

    if (item.project) {
      actions.push({
        key: 'view-project',
        label: t('list.workloads.actions.viewProject.title'),
        onPress: () => {
          router.push(`/projects/${item.projectId}`);
        },
      });
    }

    if (canBeDeleted) {
      actions.push({
        key: 'delete',
        label: t('list.workloads.actions.delete.title'),
        color: 'danger' as const,
        startContent: <IconTrash />,
        onPress: (w: WorkloadWithMetrics) => {
          setWorkloadSelected(w);
          onDeleteWorkloadModalOpen();
        },
      });
    }

    return actions;
  };

  const typeFilterItems = useMemo(
    () => getWorkloadTypeFilterItems(workloadsT),
    [workloadsT],
  );

  const statusFilterItems = useMemo(
    () => getWorkloadStatusFilterItems(workloadsT),
    [workloadsT],
  );

  const filterConfig = useMemo(
    () => ({
      search: {
        name: 'search',
        label: workloadsT('list.filters.search.placeholder'),
        placeholder: workloadsT('list.filters.search.placeholder'),
        type: FilterComponentType.TEXT,
      },
      type: {
        name: 'type',
        label: workloadsT('list.filters.type.label'),
        placeholder: workloadsT('list.filters.status.label'),
        type: FilterComponentType.DROPDOWN,
        defaultSelectedValues: defaultTypeSet.map(String),
        fields: typeFilterItems,
      },
      status: {
        name: 'status',
        label: workloadsT('list.filters.status.label'),
        placeholder: workloadsT('list.filters.status.label'),
        type: FilterComponentType.DROPDOWN,
        defaultSelectedValues: defaultStatusSet.map(String),
        fields: statusFilterItems,
      },
    }),
    [workloadsT, typeFilterItems, statusFilterItems],
  );

  const operatorMapping = {
    search: FilterOperator.CONTAINS,
    type: FilterOperator.EQ,
    status: FilterOperator.EQ,
  };

  const serverSideFilterMapping: Partial<
    Record<string, (keyof WorkloadWithMetrics)[]>
  > = {
    search: ['displayName'],
    type: ['type'],
    status: ['status'],
  };

  return (
    <div>
      <ActionsToolbar
        filterConfig={filterConfig}
        onRefresh={refetchClusterWorkloadsMetrics}
        updatedTimestamp={clusterWorkloadsMetricsUpdatedAt}
        isRefreshing={isClusterWorkloadsMetricsLoading}
        onFilterChange={(filters) => {
          const serverSideFilters =
            convertToServerSideFilterParams<WorkloadWithMetrics>(
              filters as FilterValueMap,
              operatorMapping,
              serverSideFilterMapping,
            );
          setFilters(serverSideFilters);
        }}
      />
      <ServerSideDataTable
        filters={filters}
        handleDataRequest={handleWorkloadsTableParamsChange}
        total={clusterWorkloadsMetrics?.pagination?.total ?? 0}
        data={workloadsWithProjects}
        columns={columns}
        customRenderers={customRenderers}
        customSortFieldMapper={sortFieldMapper}
        defaultSortByField={ClusterWorkloadsTableField.CREATED_AT}
        defaultSortDirection={SortDirection.DESC}
        rowActions={rowActions}
        onRowPressed={(id: string) => {
          router.push(`/workloads/${id}`);
        }}
        translation={t}
        idKey="id"
        translationKeyPrefix="workloads"
        isLoading={isClusterWorkloadsMetricsLoading}
      />
      <DeleteWorkloadModal
        isOpen={isDeleteWorkloadModalOpen}
        onOpenChange={onOpenChange}
        workload={workloadSelected}
        onConfirmAction={deleteWorkloadMutation}
      />
    </div>
  );
};

export default ClusterWorkloadsTable;
