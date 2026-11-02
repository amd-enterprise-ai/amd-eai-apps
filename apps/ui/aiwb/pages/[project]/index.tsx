// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useMemo, useRef, useState } from 'react';

import type { GetServerSidePropsContext } from 'next/types';
import { useTranslation } from 'next-i18next';

import {
  fetchProjectCpuUsage,
  fetchProjectGPUDeviceUtilization,
  fetchProjectGPUMemoryUtilization,
  fetchProjectQuota,
  fetchProjectSystemMemory,
  fetchProjectWorkloadStats,
} from '@/lib/app/projects';
import { getPageTranslations } from '@/lib/server/i18n';

import { getCurrentTimeRange } from '@amdenterpriseai/utils/app';

import { TimeRangePeriod } from '@amdenterpriseai/types';
import {
  TimeRange,
  TimeSeriesAllocationData,
  TimeSeriesDataPoint,
} from '@amdenterpriseai/types';

import {
  CPUCoreUsageCard,
  GPUDeviceUsageCard,
  GPUMemoryUsageCard,
  ProjectWorkloadsStatsCard,
  NamespaceWorkloadsTable,
  SystemMemoryUsageCard,
} from '@/components/features/projects';
import {
  AiwbDocsPage,
  aiwbDocumentationMapping,
  ChartTimeSelector,
  RelevantDocs,
} from '@amdenterpriseai/components';

import { useProject } from '@/contexts/ProjectContext';
import {
  DOCS_WORKBENCH_BASE,
  WithDocumentationLink,
} from '@amdenterpriseai/utils/app';
import { useIsLoading, useLastQueryUpdated } from '@amdenterpriseai/hooks';

const GPU_MEMORY_UTILIZATION_NUMERATOR_LABEL = 'gpu_memory_utilization';
const GPU_MEMORY_UTILIZATION_DENOMINATOR_LABEL = 'allocated_gpu_vram';
const GPU_DEVICE_UTILIZATION_NUMERATOR_LABEL = 'gpu_device_utilization';
const GPU_DEVICE_UTILIZATION_DENOMINATOR_LABEL = 'allocated_gpus';
const CPU_USAGE_NUMERATOR_LABEL = 'cpu_usage';
const CPU_USAGE_DENOMINATOR_LABEL = 'allocated_cpu';
const SYSTEM_MEMORY_NUMERATOR_LABEL = 'system_memory_usage';
const SYSTEM_MEMORY_DENOMINATOR_LABEL = 'allocated_system_memory';

export const getLatestValue = (
  points: TimeSeriesDataPoint[],
): number | null => {
  for (let i = points.length - 1; i >= 0; i--) {
    const value = points[i]?.value;
    if (value != null) return value;
  }
  return null;
};

export const isOverAllocatedQuota = (
  hasDedicatedQuota: boolean,
  gpuCount: number | null | undefined,
  latestUsage: number | null,
): boolean =>
  hasDedicatedQuota && latestUsage != null && latestUsage > (gpuCount ?? 0);

const ProjectDashboardPage: React.FC & WithDocumentationLink = () => {
  const { t } = useTranslation(['projects', 'workloads', 'models']);
  const { activeProject, isStandaloneMode } = useProject();
  const queryClient = useQueryClient();

  const namespaceMetricsQueryKeyPrefix = useMemo(
    () => ['project', activeProject, 'metrics'] as readonly string[],
    [activeProject],
  );

  const [timeRange, setTimeRange] = useState<TimeRange>(
    getCurrentTimeRange(TimeRangePeriod['15M']),
  );
  const currentTimePeriod = useRef<TimeRangePeriod>(TimeRangePeriod['15M']);

  const { data: namespaceStats, isLoading: isNamespaceStatsLoading } = useQuery(
    {
      queryKey: ['project', activeProject, 'stats'],
      queryFn: () => fetchProjectWorkloadStats(activeProject as string),
      enabled: !!activeProject,
    },
  );

  const { data: projectQuota } = useQuery({
    queryKey: ['project', activeProject, 'quota'],
    queryFn: () => fetchProjectQuota(activeProject as string),
    enabled: !!activeProject && !isStandaloneMode,
  });

  const {
    data: namespaceGPUMemoryUtilization,
    isLoading: isNamespaceGPUMemoryUtilizationLoading,
  } = useQuery({
    queryKey: [
      ...namespaceMetricsQueryKeyPrefix,
      'gpu-memory-utilization',
      {
        start: timeRange.start.toISOString(),
        end: timeRange.end.toISOString(),
      },
    ],
    queryFn: () => {
      return fetchProjectGPUMemoryUtilization(
        activeProject as string,
        timeRange.start,
        timeRange.end,
      );
    },
    enabled: !!activeProject,
  });

  const {
    data: namespaceGPUDeviceUtilization,
    isLoading: isNamespaceGPUDeviceUtilizationLoading,
  } = useQuery({
    queryKey: [
      ...namespaceMetricsQueryKeyPrefix,
      'gpu-device-utilization',
      {
        start: timeRange.start.toISOString(),
        end: timeRange.end.toISOString(),
      },
    ],
    queryFn: () => {
      return fetchProjectGPUDeviceUtilization(
        activeProject as string,
        timeRange.start,
        timeRange.end,
      );
    },
    enabled: !!activeProject,
  });

  const { data: namespaceCpuUsage, isLoading: isNamespaceCpuUsageLoading } =
    useQuery({
      queryKey: [
        ...namespaceMetricsQueryKeyPrefix,
        'cpu-usage',
        {
          start: timeRange.start.toISOString(),
          end: timeRange.end.toISOString(),
        },
      ],
      queryFn: () => {
        return fetchProjectCpuUsage(
          activeProject as string,
          timeRange.start,
          timeRange.end,
        );
      },
      enabled: !!activeProject,
    });

  const {
    data: namespaceSystemMemory,
    isLoading: isNamespaceSystemMemoryLoading,
  } = useQuery({
    queryKey: [
      ...namespaceMetricsQueryKeyPrefix,
      'system-memory-usage',
      {
        start: timeRange.start.toISOString(),
        end: timeRange.end.toISOString(),
      },
    ],
    queryFn: () => {
      return fetchProjectSystemMemory(
        activeProject as string,
        timeRange.start,
        timeRange.end,
      );
    },
    enabled: !!activeProject,
  });

  const namespaceGPUMemoryUtilizationChartData: TimeSeriesAllocationData =
    useMemo(() => {
      if (!namespaceGPUMemoryUtilization?.data)
        return { numerator: [], denominator: [] };
      const utilized = namespaceGPUMemoryUtilization.data.find(
        (s) => s.metadata?.label === GPU_MEMORY_UTILIZATION_NUMERATOR_LABEL,
      );
      const allocated = namespaceGPUMemoryUtilization.data.find(
        (s) => s.metadata?.label === GPU_MEMORY_UTILIZATION_DENOMINATOR_LABEL,
      );
      return {
        numerator: utilized?.values ?? [],
        denominator: allocated?.values ?? [],
      };
    }, [namespaceGPUMemoryUtilization]);

  const namespaceGPUDeviceUtilizationChartData: TimeSeriesAllocationData =
    useMemo(() => {
      if (!namespaceGPUDeviceUtilization?.data)
        return { numerator: [], denominator: [] };
      const utilized = namespaceGPUDeviceUtilization.data.find(
        (s) => s.metadata?.label === GPU_DEVICE_UTILIZATION_NUMERATOR_LABEL,
      );
      const allocated = namespaceGPUDeviceUtilization.data.find(
        (s) => s.metadata?.label === GPU_DEVICE_UTILIZATION_DENOMINATOR_LABEL,
      );
      return {
        numerator: utilized?.values ?? [],
        denominator: allocated?.values ?? [],
      };
    }, [namespaceGPUDeviceUtilization]);

  const namespaceCpuUsageChartData: TimeSeriesAllocationData = useMemo(() => {
    if (!namespaceCpuUsage?.data) return { numerator: [], denominator: [] };
    const used = namespaceCpuUsage.data.find(
      (s) => s.metadata?.label === CPU_USAGE_NUMERATOR_LABEL,
    );
    const allocated = namespaceCpuUsage.data.find(
      (s) => s.metadata?.label === CPU_USAGE_DENOMINATOR_LABEL,
    );
    return {
      numerator: used?.values ?? [],
      denominator: allocated?.values ?? [],
    };
  }, [namespaceCpuUsage]);

  const namespaceSystemMemoryChartData: TimeSeriesAllocationData =
    useMemo(() => {
      if (!namespaceSystemMemory?.data)
        return { numerator: [], denominator: [] };
      const used = namespaceSystemMemory.data.find(
        (s) => s.metadata?.label === SYSTEM_MEMORY_NUMERATOR_LABEL,
      );
      const allocated = namespaceSystemMemory.data.find(
        (s) => s.metadata?.label === SYSTEM_MEMORY_DENOMINATOR_LABEL,
      );
      return {
        numerator: used?.values ?? [],
        denominator: allocated?.values ?? [],
      };
    }, [namespaceSystemMemory]);

  const handleTimeBoundChange = useCallback(
    (timePeriod: TimeRangePeriod, timeRange: TimeRange) => {
      currentTimePeriod.current = timePeriod as TimeRangePeriod;
      setTimeRange(timeRange);
    },
    [setTimeRange, currentTimePeriod],
  );

  const handleRefresh = useCallback(() => {
    setTimeRange(getCurrentTimeRange(currentTimePeriod.current));
    queryClient.invalidateQueries({
      queryKey: ['project', activeProject, 'workloads'],
    });
    queryClient.resetQueries({
      queryKey: ['project', activeProject, 'stats'],
    });
  }, [queryClient, activeProject]);

  const isMetricsLoading = useIsLoading(namespaceMetricsQueryKeyPrefix);

  const dataLastUpdatedAt = useLastQueryUpdated(namespaceMetricsQueryKeyPrefix);

  const borrowedQuotaTooltip =
    projectQuota?.isQuotaManaged && projectQuota.quotas.gpuCount === 0
      ? `${t('dashboard.overview.borrowedQuota.title')}: ${t('dashboard.overview.borrowedQuota.description')}`
      : undefined;

  const hasDedicatedQuota =
    !!projectQuota?.isQuotaManaged && !!projectQuota.quotas.gpuCount;

  // Per-resource quota flags: the ceiling is a project "allocation" only if the project
  // has a dedicated quota for THAT resource; otherwise it's a cluster-capacity fallback
  // labeled "available" — mirrors how the GPU card keys off gpuCount.
  const hasCpuQuota =
    !!projectQuota?.isQuotaManaged && !!projectQuota.quotas.cpuMilliCores;
  const hasMemoryQuota =
    !!projectQuota?.isQuotaManaged && !!projectQuota.quotas.memoryBytes;

  const latestGpuDeviceUsage = getLatestValue(
    namespaceGPUDeviceUtilizationChartData.numerator,
  );

  const isOverAllocated = isOverAllocatedQuota(
    hasDedicatedQuota,
    projectQuota?.quotas.gpuCount,
    latestGpuDeviceUsage,
  );

  const overAllocatedTooltip = isOverAllocated
    ? `${t('dashboard.overview.overAllocatedQuota.title')}: ${t('dashboard.overview.overAllocatedQuota.description')}`
    : undefined;

  const deviceUsageAlertTooltip = borrowedQuotaTooltip ?? overAllocatedTooltip;

  return (
    <div className="min-h-full flex flex-col">
      <div className="flex-1 flex flex-col gap-8 mt-8">
        <div className="flex flex-col justify-center">
          <div className="mb-8 flex flex-wrap items-center justify-between gap-4">
            <h3>{t('dashboard.overview.title')}</h3>
            <ChartTimeSelector
              onTimeRangeChange={handleTimeBoundChange}
              initialTimePeriod={TimeRangePeriod['15M']}
              translationPrefix="timeRange"
              onChartsRefresh={handleRefresh}
              isFetching={isMetricsLoading}
              lastFetchedTimestamp={dataLastUpdatedAt}
              periods={[
                TimeRangePeriod['15M'],
                TimeRangePeriod['30M'],
                TimeRangePeriod['1H'],
                TimeRangePeriod['24H'],
                TimeRangePeriod['7D'],
              ]}
            />
          </div>
          <div className="flex justify-center grow">
            <div className="grid w-full max-w-[1800px] gap-4 grid-cols-1 min-[1100px]:grid-cols-3">
              <div className="flex justify-end">
                <ProjectWorkloadsStatsCard
                  isLoading={isNamespaceStatsLoading}
                  projectName={activeProject ?? 'Namespace'}
                  totalWorkloads={namespaceStats?.total ?? 0}
                  data={namespaceStats?.statusCounts ?? []}
                />
              </div>
              <GPUDeviceUsageCard
                data={namespaceGPUDeviceUtilizationChartData}
                isLoading={isNamespaceGPUDeviceUtilizationLoading}
                alertTooltip={deviceUsageAlertTooltip}
                hasDedicatedQuota={hasDedicatedQuota}
                fillHeight
              />
              <GPUMemoryUsageCard
                data={namespaceGPUMemoryUtilizationChartData}
                isLoading={isNamespaceGPUMemoryUtilizationLoading}
                alertTooltip={borrowedQuotaTooltip}
                hasDedicatedQuota={hasDedicatedQuota}
                fillHeight
              />
              <CPUCoreUsageCard
                data={namespaceCpuUsageChartData}
                isLoading={isNamespaceCpuUsageLoading}
                hasDedicatedQuota={hasCpuQuota}
                fillHeight
              />
              <SystemMemoryUsageCard
                data={namespaceSystemMemoryChartData}
                isLoading={isNamespaceSystemMemoryLoading}
                hasDedicatedQuota={hasMemoryQuota}
                fillHeight
              />
            </div>
          </div>
        </div>
        <div className="flex flex-col gap-8">
          <h3>{t('dashboard.workloads.title')}</h3>
          <NamespaceWorkloadsTable namespace={activeProject as string} />
        </div>
      </div>
      <RelevantDocs docs={aiwbDocumentationMapping[AiwbDocsPage.DASHBOARD]} />
    </div>
  );
};

ProjectDashboardPage.documentationLink = `${DOCS_WORKBENCH_BASE}/dashboard.html`;

export default ProjectDashboardPage;

export async function getServerSideProps(context: GetServerSidePropsContext) {
  const { locale = 'en', params } = context;
  const project = params?.project as string;

  try {
    const translations = await getPageTranslations(locale, [
      'projects',
      'workloads',
      'models',
    ]);

    const breadcrumb = [
      {
        title:
          translations._nextI18Next?.initialI18nStore[locale]?.common?.pages
            ?.dashboard?.title,
        href: `/${project}/`,
      },
    ];

    return {
      props: {
        ...translations,
        pageBreadcrumb: breadcrumb,
      },
    };
  } catch (error) {
    return {
      redirect: {
        destination: '/',
        permanent: false,
      },
    };
  }
}
