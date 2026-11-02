// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';

import { useTranslation } from 'next-i18next';
import router from 'next/router';

import { fetchNodeWorkloadsMetrics } from '@/services/app';
import { getClusterNodeQueryKeyPrefix } from '@/utils/cluster-nodes';
import { getClusterProjects } from '@/services/app';

import { displayMegabytesInGigabytes } from '@amdenterpriseai/utils/app';
import { displayTimestamp } from '@amdenterpriseai/utils/app';
import { getWorkloadStatusVariants } from '@/utils/workloads';
import { getWorkloadTypeVariants } from '@amdenterpriseai/utils/app';

import { TableColumns } from '@amdenterpriseai/types';
import { SortDirection } from '@amdenterpriseai/types';
import { ProjectBasicInfo } from '@/types/projects';

import { NodeWorkloadsTableField } from '@/types/enums/node-workloads-table-field';

import {
  NodeWorkloadWithMetrics,
  NodeWorkloadsMetricsResponse,
} from '@/types/workloads';

import {
  ChipDisplay,
  ClientSideDataTable,
  StatusDisplay,
} from '@amdenterpriseai/components';

import { WorkloadGpuDevicesDetail } from './WorkloadGpuDevicesDetail';

interface Props {
  clusterId: string;
  nodeId: string;
  nodeName: string;
}

const columns: TableColumns<NodeWorkloadsTableField | null> = [
  { key: NodeWorkloadsTableField.NAME, sortable: true },
  { key: NodeWorkloadsTableField.TYPE, sortable: true },
  { key: NodeWorkloadsTableField.STATUS, sortable: true },
  { key: NodeWorkloadsTableField.GPU_DEVICES },
  { key: NodeWorkloadsTableField.VRAM },
  { key: NodeWorkloadsTableField.CREATED_AT, sortable: true },
  { key: NodeWorkloadsTableField.PROJECT },
];

export const NodeWorkloadsTable: React.FC<Props> = ({
  clusterId,
  nodeId,
  nodeName,
}) => {
  const { t } = useTranslation('clusters');
  const { t: workloadsT } = useTranslation('workloads');

  const {
    data: nodeWorkloadsData,
    isLoading,
    isFetching,
  } = useQuery<NodeWorkloadsMetricsResponse>({
    queryKey: [
      ...getClusterNodeQueryKeyPrefix(clusterId, nodeId),
      'workloads-metrics',
    ],
    queryFn: () => fetchNodeWorkloadsMetrics(clusterId, nodeId),
  });

  const { data: clusterProjects } = useQuery({
    queryKey: ['cluster', clusterId, 'projects'],
    queryFn: () => getClusterProjects(clusterId),
  });

  type WorkloadWithProject = NodeWorkloadWithMetrics & {
    project?: ProjectBasicInfo;
  };

  const workloadsWithProjects: WorkloadWithProject[] = useMemo(() => {
    if (!nodeWorkloadsData?.data) return [];
    if (!clusterProjects?.data) return nodeWorkloadsData.data;

    const projectsMap = new Map(
      clusterProjects.data.map((proj: ProjectBasicInfo) => [proj.id, proj]),
    );

    return nodeWorkloadsData.data.map((workload) => ({
      ...workload,
      project: projectsMap.get(workload.projectId),
    }));
  }, [nodeWorkloadsData, clusterProjects]);

  const customRenderers: Partial<
    Record<
      NodeWorkloadsTableField,
      (item: WorkloadWithProject) => React.ReactNode | string
    >
  > = {
    [NodeWorkloadsTableField.VRAM]: (item) =>
      displayMegabytesInGigabytes(item.vram),
    [NodeWorkloadsTableField.CREATED_AT]: (item) =>
      item.createdAt ? displayTimestamp(new Date(item.createdAt)) : '-',
    [NodeWorkloadsTableField.PROJECT]: (item) =>
      item.project ? item.project.name : '-',
    [NodeWorkloadsTableField.STATUS]: (item) => (
      <StatusDisplay
        type={item.status}
        variants={getWorkloadStatusVariants(workloadsT)}
      />
    ),
    [NodeWorkloadsTableField.TYPE]: (item) => (
      <ChipDisplay
        type={item.type ?? t('common:error.misc.unknownEntity')}
        variants={getWorkloadTypeVariants(workloadsT)}
      />
    ),
    [NodeWorkloadsTableField.GPU_DEVICES]: (item) => (
      <WorkloadGpuDevicesDetail
        devices={item.gpuDevices}
        nodeName={nodeName}
        devicesLabel={t('nodes.detail.workloads.gpuDevices.devices', {
          count: item.gpuDevices.length,
        })}
      />
    ),
  };

  const rowActions = useMemo(
    () => (item: WorkloadWithProject) => {
      if (!item.project) return [];
      return [
        {
          key: 'view-project',
          label: t('nodes.detail.workloads.actions.viewProject.title'),
          onPress: () => {
            router.push(`/projects/${item.projectId}`);
          },
        },
      ];
    },
    [t],
  );

  return (
    <ClientSideDataTable
      data={workloadsWithProjects}
      columns={columns}
      defaultSortByField={NodeWorkloadsTableField.CREATED_AT}
      defaultSortDirection={SortDirection.DESC}
      translation={t}
      translationKeyPrefix="nodes.detail.workloads"
      customRenderers={customRenderers}
      rowActions={rowActions}
      idKey="id"
      isLoading={isLoading}
      isFetching={isFetching}
      onRowPressed={(id: string) => {
        router.push(`/workloads/${id}`);
      }}
    />
  );
};

export default NodeWorkloadsTable;
