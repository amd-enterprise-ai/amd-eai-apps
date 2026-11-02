// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  Accordion,
  AccordionItem,
  ActionButton,
  ActionsToolbar,
  Alert,
  BarChart,
  Card,
  CardBody,
  CardHeader,
  ChartTimeSelector,
  ConfirmationModal,
  DropdownItem,
  DropdownMenu,
  Dropdown,
  DropdownTrigger,
} from '@amdenterpriseai/components';
import { useOverlayState, useSystemToast } from '@amdenterpriseai/hooks';
import {
  IconChevronDown,
  IconExternalLink,
  IconTrash,
  IconEdit,
  IconFileSettings,
  IconEye,
} from '@tabler/icons-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useMemo, useRef, useState } from 'react';

import { getServerSession } from 'next-auth';
import { useTranslation } from 'next-i18next';
import { useRouter } from 'next/router';

import { useAccessControl } from '@/hooks/useAccessControl';
import { getPageTranslations } from '@/utils/i18n';

import {
  deleteCluster as deleteClusterAPI,
  getCluster as fetchCluster,
  getClusterNodes as fetchClusterNodes,
} from '@/services/app';
import { fetchGPUDeviceUtilizationByClusterId } from '@/services/app';
import { getClusterProjects as fetchClusterProjects } from '@/services/app';
import { getClusterWorkloadsStats as fetchClusterWorkloadsStats } from '@/services/app';
import {
  getCluster,
  getClusterNodes,
  getClusterProjects,
} from '@/services/server';
import { getClusterWorkloadsStats } from '@/services/server';

import { doesProjectDataNeedToBeRefreshed } from '@/utils/projects';
import {
  getTickGap,
  isHttpUrl,
  rollupTimeSeriesData,
  transformTimeSeriesDataToChartData,
} from '@amdenterpriseai/utils/app';
import { getFilteredData } from '@amdenterpriseai/utils/app';
import { displayFixedNumber } from '@amdenterpriseai/utils/app';
import { getCurrentTimeRange } from '@amdenterpriseai/utils/app';
import {
  DOCS_RESOURCE_MANAGER_BASE,
  WithDocumentationLink,
} from '@amdenterpriseai/utils/app';
import { authOptions } from '@amdenterpriseai/utils/server';

import { Cluster } from '@/types/clusters';
import { ClusterNodesResponse } from '@/types/clusters';
import { ProjectsResponse } from '@/types/projects';
import { FilterComponentType } from '@amdenterpriseai/types';
import { ClusterNode } from '@/types/clusters';
import { TimeRangePeriod } from '@amdenterpriseai/types';
import { ClientSideDataFilter, FilterValueMap } from '@amdenterpriseai/types';
import { TimeRange, TimeSeriesResponse } from '@amdenterpriseai/types';
import { WorkloadStatusStatsResponse } from '@/types/metrics';
import { ClusterProjectsResponse, Project } from '@/types/projects';

import { ClusterStats, EditCluster } from '@/components/features/clusters';
import { ClusterNodesTable } from '@/components/features/clusters/ClusterNodes';
import { ProjectTable } from '@/components/features/projects';
import { APIRequestError } from '@amdenterpriseai/utils/app';
import { DEFAULT_REFETCH_INTERVAL_FOR_PENDING_DATA } from '@amdenterpriseai/utils/app';
import ClusterKubeConfig from '@/components/features/clusters/ClusterKubeConfig';

const translationKeySet = 'clusters';

interface Props {
  cluster: Cluster;
  clusterNodesResponse: ClusterNodesResponse;
  projectsResponse: ClusterProjectsResponse;
  workloadsStats: WorkloadStatusStatsResponse;
}

const ClusterPage: React.FC<Props> & WithDocumentationLink = ({
  cluster,
  clusterNodesResponse,
  projectsResponse,
  workloadsStats,
}) => {
  const router = useRouter();
  const { id } = router.query;
  const { t } = useTranslation(translationKeySet);
  const { toast } = useSystemToast();
  const { isAdministrator } = useAccessControl();
  const queryClient = useQueryClient();

  const {
    isOpen: isEditClusterOpen,
    onOpen: onEditClusterOpen,
    onOpenChange: onEditClusterOpenChange,
  } = useOverlayState();

  const {
    isOpen: isDeleteClusterModalOpen,
    onOpen: onDeleteClusterModalOpen,
    onOpenChange: onDeleteClusterModalOpenChange,
  } = useOverlayState();

  const { mutate: deleteCluster, isPending: isDeleteClusterPending } =
    useMutation({
      mutationFn: deleteClusterAPI,
      onSuccess: () => {
        onDeleteClusterModalOpenChange();
        queryClient.invalidateQueries({ queryKey: ['clusters'] });
        toast.success(t('list.actions.delete.notification.success'));
        router.push('/clusters');
      },
      onError: (error) => {
        onDeleteClusterModalOpenChange();
        toast.error(
          t('list.actions.delete.notification.error'),
          error as APIRequestError,
        );
      },
    });

  const [clusterNodesFilters, setClusterNodesFilters] = useState<
    ClientSideDataFilter<ClusterNode>[]
  >([]);
  const [projectFilters, setProjectFilters] = useState<
    ClientSideDataFilter<Project>[]
  >([]);
  const [timeRange, setTimeRange] = useState<TimeRange>(
    getCurrentTimeRange(TimeRangePeriod['1H']),
  );
  const currentTimePeriod = useRef<TimeRangePeriod>(TimeRangePeriod['1H']);

  const { data: clusterData } = useQuery<Cluster>({
    queryKey: ['cluster'],
    queryFn: () => fetchCluster(id as string),
    initialData: cluster,
  });

  const { data: clusterProjects } = useQuery<ClusterProjectsResponse>({
    queryKey: ['cluster', 'projects'],
    queryFn: () => fetchClusterProjects(id as string),
    initialData: projectsResponse,
    refetchInterval: (query) => {
      return !query.state.data ||
        doesProjectDataNeedToBeRefreshed(query.state.data.data)
        ? DEFAULT_REFETCH_INTERVAL_FOR_PENDING_DATA
        : false;
    },
  });

  const { data: clusterNodesData } = useQuery<ClusterNodesResponse>({
    queryKey: ['cluster', 'nodes'],
    queryFn: () => fetchClusterNodes(id as string),
    initialData: clusterNodesResponse,
  });

  const { data: clusterWorkloadsStats } = useQuery<WorkloadStatusStatsResponse>(
    {
      queryKey: ['cluster', 'workloads', 'stats'],
      queryFn: () => fetchClusterWorkloadsStats(id as string),
      initialData: workloadsStats,
    },
  );

  const {
    data: gpuDeviceUsageData,
    isFetching: isGPUDeviceUsageDataFetching,
    dataUpdatedAt: gpuDeviceUsageDataUpdatedAt,
  } = useQuery<TimeSeriesResponse>({
    queryKey: [
      'gpu-device-utilization',
      cluster.id,
      {
        start: timeRange.start.toISOString(),
        end: timeRange.end.toISOString(),
      },
    ],
    queryFn: () => {
      return fetchGPUDeviceUtilizationByClusterId(
        id as string,
        timeRange.start,
        timeRange.end,
      );
    },
  });

  const handleTimeBoundChange = (
    timePeriod: TimeRangePeriod,
    timeRange: TimeRange,
  ) => {
    currentTimePeriod.current = timePeriod as TimeRangePeriod;
    setTimeRange(timeRange);
  };

  const filteredClusterData = useMemo(() => {
    if (!clusterNodesData?.data) {
      return [];
    }

    return getFilteredData(clusterNodesData.data, clusterNodesFilters);
  }, [clusterNodesData?.data, clusterNodesFilters]);

  const filteredProjects = useMemo(() => {
    if (!clusterProjects.data) {
      return [];
    }
    return getFilteredData(clusterProjects.data, projectFilters);
  }, [clusterProjects.data, projectFilters]);

  const deviceChartData = useMemo(() => {
    if (!gpuDeviceUsageData) {
      return null;
    }
    const processedData =
      gpuDeviceUsageData.data.length > 4
        ? rollupTimeSeriesData(
            gpuDeviceUsageData,
            t('common:charts.category.others'),
            'project',
          )
        : gpuDeviceUsageData.data;

    return transformTimeSeriesDataToChartData(
      processedData,
      gpuDeviceUsageData.range.timestamps,
      'project',
    );
  }, [gpuDeviceUsageData, t]);

  const deviceUtilizationChart = useMemo(
    () => (
      <BarChart
        type="stacked"
        minValue={0}
        maxValue={100}
        className="h-64"
        tickGap={getTickGap(currentTimePeriod?.current)}
        data={deviceChartData?.data || []}
        onValueChange={() => {}}
        index="date"
        categories={deviceChartData?.categories || []}
        showTooltipOnNull
        valueFormatter={(number: number) => {
          return typeof number === 'number'
            ? `${displayFixedNumber(number, 2)}%`
            : t('common:charts.nodata');
        }}
        isLoading={isGPUDeviceUsageDataFetching && !deviceChartData}
      />
    ),
    [deviceChartData, isGPUDeviceUsageDataFetching, t],
  );

  const handleChartsRefresh = useCallback(() => {
    setTimeRange(getCurrentTimeRange(currentTimePeriod.current));
  }, []);

  const handleFilterChange = useCallback(
    (filters: FilterValueMap) => {
      const newClusterNodeFilters: ClientSideDataFilter<ClusterNode>[] = [];
      const newProjectFilters: ClientSideDataFilter<Project>[] = [];

      if (filters.search) {
        newClusterNodeFilters.push({
          values: filters.search,
          compositeFields: [
            { field: 'name' },
            { field: 'gpuInfo', path: 'name' },
          ],
        });
        newProjectFilters.push({
          values: filters.search,
          field: 'name',
        });
      }

      setClusterNodesFilters(newClusterNodeFilters);
      setProjectFilters(newProjectFilters);
    },
    [setClusterNodesFilters, setProjectFilters],
  );

  const {
    isOpen: isClusterKubeConfigOpen,
    onOpen: onClusterKubeConfigOpen,
    onOpenChange: onClusterKubeConfigChange,
  } = useOverlayState();

  const filterConfig = useMemo(
    () => ({
      search: {
        name: 'search',
        className: 'min-w-72',
        label: t('list.filter.search.label'),
        placeholder: t('list.filter.search.placeholder'),
        type: FilterComponentType.TEXT,
      },
    }),
    [t],
  );

  return (
    <div className="inline-flex flex-col w-full h-full max-h-full">
      <div className="md:py-4 lg:py-6 flex justify-between">
        <ActionsToolbar
          filterConfig={filterConfig}
          onFilterChange={handleFilterChange}
          endContent={
            <Dropdown>
              <DropdownTrigger>
                <ActionButton
                  aria-label={t('common:list.actions.label') || ''}
                  endContent={<IconChevronDown size={16} />}
                >
                  {t('common:list.actions.label')}
                </ActionButton>
              </DropdownTrigger>
              <DropdownMenu
                aria-label={t('common:list.actions.label') || ''}
                disabledKeys={[
                  ...(!clusterData?.kubeApiUrl ? ['viewConfig'] : []),
                  ...(!clusterData?.workbenchBaseUrl ||
                  !isHttpUrl(clusterData.workbenchBaseUrl)
                    ? ['viewInAiwb']
                    : []),
                  ...(!isAdministrator
                    ? ['edit', 'delete', 'viewWorkloads']
                    : []),
                ]}
              >
                {!isAdministrator ? (
                  <DropdownItem
                    key="teamMemberAlert"
                    className="pointer-events-none"
                  >
                    <Alert
                      status="warning"
                      isTight
                      title={t('actions.teamMemberAlert.title')}
                      hideIcon
                      className="w-[240px]"
                      description={t('actions.teamMemberAlert.description')}
                    />
                  </DropdownItem>
                ) : null}
                <DropdownItem
                  aria-label={t('workloads.actions.view') || ''}
                  onPress={() => router.push(`/clusters/${id}/workloads`)}
                  key="viewWorkloads"
                  startContent={<IconEye />}
                >
                  {t('workloads.actions.view')}
                </DropdownItem>
                <DropdownItem
                  key="edit"
                  onPress={onEditClusterOpen}
                  startContent={<IconEdit />}
                >
                  {t('list.actions.edit.label')}
                </DropdownItem>

                <DropdownItem
                  key="viewConfig"
                  onPress={onClusterKubeConfigOpen}
                  startContent={<IconFileSettings />}
                >
                  {t('config.button')}
                </DropdownItem>
                <DropdownItem
                  key="viewInAiwb"
                  onPress={() => {
                    if (
                      clusterData?.workbenchBaseUrl &&
                      isHttpUrl(clusterData.workbenchBaseUrl)
                    ) {
                      window.open(
                        clusterData.workbenchBaseUrl,
                        '_blank',
                        'noopener,noreferrer',
                      );
                    }
                  }}
                  showDivider
                  startContent={<IconExternalLink />}
                >
                  {t('actions.viewInAiwb.label')}
                </DropdownItem>

                <DropdownItem
                  key="delete"
                  variant="danger"
                  onPress={onDeleteClusterModalOpen}
                  startContent={<IconTrash />}
                >
                  {t('list.actions.delete.label')}
                </DropdownItem>
              </DropdownMenu>
            </Dropdown>
          }
        />
      </div>
      <div className="flex flex-col gap-4">
        <ClusterStats
          cluster={clusterData}
          workloadsStats={clusterWorkloadsStats}
        />
        <Card>
          <CardHeader className="pb-2 flex flex-row items-center justify-between">
            <h4>
              {t('allocationAndWorkloads.charts.gpuDeviceUtilization.title')}
            </h4>
            <ChartTimeSelector
              onTimeRangeChange={handleTimeBoundChange}
              initialTimePeriod={TimeRangePeriod['1H']}
              translationPrefix="timeRange"
              isFetching={isGPUDeviceUsageDataFetching}
              onChartsRefresh={handleChartsRefresh}
              lastFetchedTimestamp={
                gpuDeviceUsageDataUpdatedAt
                  ? new Date(gpuDeviceUsageDataUpdatedAt)
                  : undefined
              }
            />
          </CardHeader>
          <CardBody className="pt-0 mt-4">{deviceUtilizationChart}</CardBody>
        </Card>
      </div>
      <Accordion
        defaultExpandedKeys={['cluster-nodes', 'cluster-quotas']}
        selectionMode="multiple"
      >
        <AccordionItem
          title={t('projects.title')}
          aria-label={t('projects.title')!}
          key="cluster-quotas"
          classNames={{ title: 'uppercase' }}
        >
          <ProjectTable projects={filteredProjects} />
        </AccordionItem>
        <AccordionItem
          title={t('nodes.title')}
          aria-label={t('nodes.title')!}
          key="cluster-nodes"
          classNames={{ title: 'uppercase' }}
        >
          <ClusterNodesTable
            clusterId={id as string}
            clusterNodes={filteredClusterData}
          />
        </AccordionItem>
      </Accordion>

      <ClusterKubeConfig
        isOpen={isClusterKubeConfigOpen}
        onOpenChange={onClusterKubeConfigChange}
        cluster={clusterData}
      />

      <EditCluster
        isOpen={isEditClusterOpen}
        onOpenChange={onEditClusterOpenChange}
        cluster={clusterData}
      />

      <ConfirmationModal
        confirmationButtonColor="danger"
        description={t('list.actions.delete.confirmation.description')}
        title={t('list.actions.delete.confirmation.title')}
        isOpen={isDeleteClusterModalOpen}
        loading={isDeleteClusterPending}
        onConfirm={() => deleteCluster(clusterData.id)}
        onClose={onDeleteClusterModalOpenChange}
      />
    </div>
  );
};

ClusterPage.documentationLink = `${DOCS_RESOURCE_MANAGER_BASE}/clusters/overview.html`;

export default ClusterPage;

export async function getServerSideProps(context: any) {
  const { locale } = context;

  const session = await getServerSession(context.req, context.res, authOptions);

  try {
    const [cluster, clusterNodesResponse, projectsResponse, workloadsStats] =
      await Promise.all([
        getCluster(context.params.id, session?.accessToken as string),
        getClusterNodes(context.params.id, session?.accessToken as string),
        getClusterProjects(context.params.id, session?.accessToken as string),
        getClusterWorkloadsStats(
          context.params.id,
          session?.accessToken as string,
        ),
      ]);

    const translations = await getPageTranslations(locale, [
      'projects',
      'clusters',
    ]);

    const breadcrumb = [
      {
        title:
          translations._nextI18Next?.initialI18nStore[locale]?.clusters?.title,
        href: '/clusters',
      },
      {
        title: `${cluster.name}`,
      },
    ];

    return {
      props: {
        ...translations,
        cluster,
        clusterNodesResponse,
        projectsResponse,
        workloadsStats,
        pageBreadcrumb: breadcrumb,
      },
    };
  } catch (error) {
    console.error('Cluster not found: ' + error);
    return {
      redirect: {
        destination: '/',
        permanent: false,
      },
    };
  }
}
