// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  ActionButton,
  Button,
  Card,
  CardBody,
  ChartTimeSelector,
  StatusDisplay,
} from '@amdenterpriseai/components';
import { IconArrowLeft, IconTrash } from '@tabler/icons-react';
import { useCallback, useMemo, useRef, useState } from 'react';
import {
  useQuery,
  useMutation,
  useQueryClient,
  useIsFetching,
} from '@tanstack/react-query';
import { GetServerSidePropsContext } from 'next';
import { getServerSession } from 'next-auth';
import { useTranslation } from 'next-i18next';
import { useRouter } from 'next/router';

import {
  useIsLoading,
  useLastQueryUpdated,
  useSystemToast,
} from '@amdenterpriseai/hooks';
import { getPageTranslations } from '@/utils/i18n';

import {
  getWorkloadMetrics,
  getWorkloadVramUtilization,
  getWorkloadGpuUtilization,
  getWorkloadPowerUsage,
  deleteWorkload,
} from '@/services/app';

import { getWorkload } from '@/services/server/workloads';
import { formatDeviceName } from '@/components/features/clusters/NodeWorkloadsTable/WorkloadGpuDevicesDetail';
import { getClusterNodes } from '@/services/server/clusters';

import { getWorkloadStatusVariants } from '@/utils/workloads';
import { getCurrentTimeRange } from '@amdenterpriseai/utils/app';
import {
  DOCS_RESOURCE_MANAGER_BASE,
  WithDocumentationLink,
} from '@amdenterpriseai/utils/app';
import { authOptions } from '@amdenterpriseai/utils/server';
import { APIRequestError } from '@amdenterpriseai/utils/app';

import { TimeRangePeriod } from '@amdenterpriseai/types';
import { ClusterNode } from '@/types/clusters';

import { WorkloadResponse, WorkloadMetricsDetails } from '@/types/workloads';
import { WorkloadStatus } from '@/types/enums/workloads';

import DeleteWorkloadModal from '@/components/features/workloads/DeleteWorkloadModal';
import { GpuDeviceMetricsGrid } from '@/components/features/workloads/GpuDeviceMetricsGrid';
import { GpuMetricsLoadingSkeleton } from '@/components/features/workloads/GpuMetricsLoadingSkeleton';
import { WorkloadBasicInfoCard } from '@/components/features/workloads/WorkloadBasicInfoCard';
import { WorkloadClusterResourcesCard } from '@/components/features/workloads/WorkloadClusterResourcesCard';
import { WorkloadTimelineCard } from '@/components/features/workloads/WorkloadTimelineCard';

interface Props {
  pageBreadcrumb?: { title: string; href?: string }[];
  workload: WorkloadResponse;
  clusterNodes: ClusterNode[];
}

const WorkloadDetailPage: React.FC<Props> & WithDocumentationLink = ({
  workload,
  clusterNodes,
}) => {
  const { t } = useTranslation(['workloads', 'common']);
  const { t: workloadsT } = useTranslation('workloads');
  const router = useRouter();
  const queryClient = useQueryClient();
  const { toast } = useSystemToast();
  const { id } = router.query;

  const [timeRange, setTimeRange] = useState(() =>
    getCurrentTimeRange(TimeRangePeriod['1H']),
  );
  const currentTimePeriod = useRef<TimeRangePeriod>(TimeRangePeriod['1H']);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);

  const { data: workloadMetrics, refetch: refetchWorkloadMetrics } =
    useQuery<WorkloadMetricsDetails>({
      queryKey: ['workload', id, 'metrics'],
      queryFn: async () => {
        const data = await getWorkloadMetrics(id as string);
        if (data == null) throw new Error('Workload metrics not found');
        return data;
      },
      enabled: !!id,
    });

  const gpuMetricsParams = {
    start: timeRange.start.toISOString(),
    end: timeRange.end.toISOString(),
  };
  const queryKeyBase = ['workload', id as string] as const;

  const vramQuery = useQuery({
    queryKey: [
      ...queryKeyBase,
      'vram-utilization',
      gpuMetricsParams.start,
      gpuMetricsParams.end,
    ],
    queryFn: () => getWorkloadVramUtilization(id as string, gpuMetricsParams),
    enabled: !!id,
  });

  const gpuUtilizationQuery = useQuery({
    queryKey: [
      ...queryKeyBase,
      'gpu-utilization',
      gpuMetricsParams.start,
      gpuMetricsParams.end,
    ],
    queryFn: () => getWorkloadGpuUtilization(id as string, gpuMetricsParams),
    enabled: !!id,
  });

  const powerQuery = useQuery({
    queryKey: [
      ...queryKeyBase,
      'power-usage',
      gpuMetricsParams.start,
      gpuMetricsParams.end,
    ],
    queryFn: () => getWorkloadPowerUsage(id as string, gpuMetricsParams),
    enabled: !!id,
  });

  const isFetchingMetrics =
    useIsFetching({
      queryKey: queryKeyBase,
    }) > 0;

  const isLoadingMetrics = useIsLoading(queryKeyBase);

  const lastUpdated = useLastQueryUpdated(queryKeyBase);

  const gpuDevices = useMemo(() => {
    const toSeries = (values: { value: number; timestamp: string }[]) =>
      values.map((v) => ({ time: v.timestamp, value: v.value }));
    const latestValue = (values: { value: number }[]) =>
      values.length > 0 ? values[values.length - 1].value : null;

    const vramDevices = vramQuery.data?.gpuDevices ?? [];
    const gpuUtilDevices = gpuUtilizationQuery.data?.gpuDevices ?? [];
    const powerDevices = powerQuery.data?.gpuDevices ?? [];

    const vramByUuid = new Map(vramDevices.map((d) => [d.gpuUuid, d]));
    const gpuUtilByUuid = new Map(gpuUtilDevices.map((d) => [d.gpuUuid, d]));
    const powerByUuid = new Map(powerDevices.map((d) => [d.gpuUuid, d]));

    const uniqueDevices = new Map(
      [...vramDevices, ...gpuUtilDevices, ...powerDevices].map((d) => [
        d.gpuUuid,
        { gpuUuid: d.gpuUuid, gpuId: d.gpuId, hostname: d.hostname },
      ]),
    );

    return Array.from(uniqueDevices.values())
      .map((base) => {
        const vram = vramByUuid.get(base.gpuUuid)?.metric?.values ?? [];
        const gpuUtil = gpuUtilByUuid.get(base.gpuUuid)?.metric?.values ?? [];
        const power = powerByUuid.get(base.gpuUuid)?.metric?.values ?? [];
        return {
          ...base,
          displayLabel: formatDeviceName(base),
          vramUtilizationPct: latestValue(vram),
          gpuUtilizationPct: latestValue(gpuUtil),
          powerUsageW: latestValue(power),
          vramUtilizationSeries: toSeries(vram),
          gpuUtilizationSeries: toSeries(gpuUtil),
          powerUsageSeries: toSeries(power),
        };
      })
      .sort(
        (a, b) =>
          a.hostname.localeCompare(b.hostname) ||
          parseInt(a.gpuId, 10) - parseInt(b.gpuId, 10),
      );
  }, [vramQuery.data, gpuUtilizationQuery.data, powerQuery.data]);

  const nodesByHostname = useMemo(
    () =>
      clusterNodes.reduce(
        (map, node) => map.set(node.name, node),
        new Map<string, ClusterNode>(),
      ),
    [clusterNodes],
  );

  const { mutate: deleteWorkloadMutation } = useMutation({
    mutationFn: deleteWorkload,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workload', id] });
      queryClient.invalidateQueries({ queryKey: ['cluster', 'workloads'] });
      toast.success(t('workloads:list.actions.delete.notification.success'));
      router.back();
    },
    onError: (error) => {
      toast.error(
        t('workloads:list.actions.delete.notification.error'),
        error as APIRequestError,
      );
    },
  });

  const handleTimeRangeChange = useCallback(
    (period: TimeRangePeriod, newTimeRange: { start: Date; end: Date }) => {
      currentTimePeriod.current = period;
      setTimeRange(newTimeRange);
    },
    [],
  );

  const handleChartsRefresh = useCallback(() => {
    const newRange = getCurrentTimeRange(currentTimePeriod.current);
    setTimeRange(newRange);
    refetchWorkloadMetrics();
  }, [refetchWorkloadMetrics]);

  const hasGpuMetrics = gpuDevices.length > 0;
  const showGpuLoadingPlaceholder = isLoadingMetrics && gpuDevices.length === 0;

  const moduleName = workload.displayName || '';

  return (
    <div className="inline-flex flex-col w-full max-w-6xl mx-auto p-4 md:p-6 gap-6">
      {/* Header: breadcrumb (back + module name + status) and actions on one row */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-2 min-w-0">
          <ActionButton
            secondary
            size="sm"
            onPress={() => router.back()}
            icon={<IconArrowLeft size={16} />}
            aria-label={t('workloads:details.actions.back')}
          />
          <span className="text-base font-medium truncate">{moduleName}</span>
          <StatusDisplay
            type={workload.status}
            variants={getWorkloadStatusVariants(workloadsT)}
          />
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Button
            color="danger"
            variant="flat"
            size="sm"
            startContent={<IconTrash size={16} />}
            isDisabled={[
              WorkloadStatus.DELETING,
              WorkloadStatus.DELETED,
            ].includes(workload.status)}
            onPress={() => setIsDeleteModalOpen(true)}
          >
            {t('workloads:details.actions.delete')}
          </Button>
        </div>
      </div>

      {/* Resource utilization */}
      <section className="flex flex-col gap-4">
        <div className="flex flex-row items-center justify-between gap-4 flex-wrap">
          <h3 className="text-base font-medium">
            {t('workloads:details.sections.resourceUtilization')}
          </h3>
          <div className="flex items-center gap-3">
            <ChartTimeSelector
              onTimeRangeChange={handleTimeRangeChange}
              onChartsRefresh={handleChartsRefresh}
              isFetching={isFetchingMetrics}
              lastFetchedTimestamp={lastUpdated}
              initialTimePeriod={TimeRangePeriod['1H']}
            />
          </div>
        </div>
        {showGpuLoadingPlaceholder ? (
          <GpuMetricsLoadingSkeleton />
        ) : !hasGpuMetrics ? (
          <Card>
            <CardBody>
              <p className="text-muted text-sm">
                {t('workloads:details.fields.noGpuMetrics')}
              </p>
            </CardBody>
          </Card>
        ) : (
          <GpuDeviceMetricsGrid
            devices={gpuDevices}
            nodesByHostname={nodesByHostname}
            clusterId={workload?.clusterId}
            isFetching={isFetchingMetrics}
          />
        )}
      </section>

      {/* Information */}
      <section>
        <h3 className="text-base font-medium mb-4">
          {t('workloads:details.sections.workloadInformation')}
        </h3>
        <div className="flex flex-col md:flex-row gap-4">
          <div className="flex flex-col gap-4 md:w-1/2">
            <WorkloadBasicInfoCard
              name={workload.displayName || ''}
              workloadId={workload.id}
              createdBy={workload.createdBy}
            />
            <WorkloadTimelineCard
              createdAt={workload.createdAt}
              updatedAt={workload.updatedAt}
              queueTime={workloadMetrics?.queueTime}
              runningTime={workloadMetrics?.runningTime}
            />
          </div>
          <div className="md:w-1/2">
            <WorkloadClusterResourcesCard
              clusterName={workloadMetrics?.clusterName}
              clusterId={workloadMetrics?.clusterId}
              nodesInUse={workloadMetrics?.nodesInUse}
              gpuDevicesInUse={workloadMetrics?.gpuDevicesInUse}
              isLoading={!workloadMetrics}
            />
          </div>
        </div>
      </section>

      <DeleteWorkloadModal
        isOpen={isDeleteModalOpen}
        onOpenChange={setIsDeleteModalOpen}
        workload={workload}
        onConfirmAction={(workloadId) => deleteWorkloadMutation(workloadId)}
      />
    </div>
  );
};

WorkloadDetailPage.documentationLink = `${DOCS_RESOURCE_MANAGER_BASE}/workloads/workload-detail.html`;

export default WorkloadDetailPage;

export async function getServerSideProps(context: GetServerSidePropsContext) {
  const locale = context.locale ?? 'en';
  const session = await getServerSession(context.req, context.res, authOptions);

  const workloadId = context.params?.id as string;

  try {
    const workload = (await getWorkload({
      accessToken: session?.accessToken as string,
      workloadId,
    })) as WorkloadResponse;

    const clusterId = workload?.clusterId;

    const clusterNodesResponse = clusterId
      ? await getClusterNodes(clusterId, session?.accessToken as string).catch(
          () => ({ data: [] }),
        )
      : { data: [] };

    const translations = await getPageTranslations(locale, ['workloads']);

    const breadcrumb = [{ title: 'Workload details' }];
    return {
      props: {
        ...translations,
        pageBreadcrumb: breadcrumb,
        workload,
        clusterNodes: clusterNodesResponse.data,
      },
    };
  } catch (error) {
    console.error('Workload retrieval failure: ' + error);
    return {
      redirect: { destination: '/', permanent: false },
    };
  }
}
