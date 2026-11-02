// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { ChartTimeSelector } from '@amdenterpriseai/components';
import { TimeRangePeriod } from '@amdenterpriseai/types';
import { TimeRange } from '@amdenterpriseai/types';
import { getCurrentTimeRange } from '@amdenterpriseai/utils/app';
import { useIsFetching, useQuery, useQueryClient } from '@tanstack/react-query';
import React, { useCallback, useMemo, useRef, useState } from 'react';
import {
  CPUCoreUsageCard,
  GPUDeviceUsageCard,
  GPUMemoryUsageCard,
  SystemMemoryUsageCard,
} from '@/components/features/projects';
import InferenceRequestsCard from './InferenceRequestsCard';
import { ScalarMetricCard, ScalarMetricConfig } from './ScalarMetricCard';
import {
  TimeseriesMetricCard,
  TimeseriesMetricConfig,
} from './TimeseriesMetricCard';
import { useProject } from '@/contexts/ProjectContext';
import { useTranslation } from 'next-i18next';
import { getTimeseriesMetric } from '@/lib/app/metrics';
import {
  displayPercentage,
  formatSeconds,
  formatTokens,
} from '@amdenterpriseai/utils/app';
import { InferenceMetricsColors } from '@/types/metrics';

const LATENCY_METRICS: TimeseriesMetricConfig[] = [
  {
    metric: 'time_to_first_token_seconds',
    localeKey: 'timeToFirstToken',
    color: InferenceMetricsColors.TIME_TO_FIRST_TOKEN,
    dataFormatter: formatSeconds,
  },
  {
    metric: 'inter_token_latency_seconds',
    localeKey: 'interTokenLatency',
    color: InferenceMetricsColors.INTER_TOKEN_LATENCY,
    dataFormatter: formatSeconds,
  },
  {
    metric: 'e2e_request_latency_seconds',
    localeKey: 'endToEndLatency',
    color: InferenceMetricsColors.END_TO_END_LATENCY,
    dataFormatter: formatSeconds,
  },
];

const SCALAR_METRICS: ScalarMetricConfig[] = [
  { metric: 'max_requests', localeKey: 'maxRequests' },
  { metric: 'min_requests', localeKey: 'minRequests' },
  {
    metric: 'avg_requests',
    localeKey: 'avgRequests',
    transform: (v) => Math.round(v * 10) / 10,
  },
  { metric: 'total_requests', localeKey: 'totalRequests' },
  { metric: 'total_tokens', localeKey: 'totalTokens', formatter: formatTokens },
  {
    metric: 'kv_cache_usage',
    localeKey: 'kvCacheUsage',
    transform: (v) => v * 100,
    formatter: displayPercentage,
  },
];

interface InferenceMetricsProps {
  workloadId: string;
  podName?: string;
}

export const InferenceMetrics: React.FC<InferenceMetricsProps> = ({
  workloadId,
  podName,
}) => {
  const { t } = useTranslation(['workloads']);
  const queryClient = useQueryClient();
  const { activeProject } = useProject();
  const namespace = activeProject;

  const [timeRange, setTimeRange] = useState<TimeRange>(
    getCurrentTimeRange(TimeRangePeriod['15M']),
  );
  const currentTimePeriod = useRef<TimeRangePeriod>(TimeRangePeriod['15M']);

  const handleTimeBoundChange = (
    timePeriod: TimeRangePeriod,
    newTimeRange: TimeRange,
  ) => {
    currentTimePeriod.current = timePeriod as TimeRangePeriod;
    setTimeRange(newTimeRange);
    queryClient.invalidateQueries({
      queryKey: ['project', namespace, 'workload', workloadId, 'metrics'],
    });
  };

  const isFetchingMetrics =
    useIsFetching({
      queryKey: ['project', namespace, 'workload', workloadId, 'metrics'],
    }) > 0;

  const metricsLastFetchedAt = useRef<Date | undefined>(undefined);
  useMemo(() => {
    if (!isFetchingMetrics) {
      metricsLastFetchedAt.current = new Date();
    }
  }, [isFetchingMetrics]);

  const handleChartsRefresh = useCallback(() => {
    setTimeRange(getCurrentTimeRange(currentTimePeriod.current));
  }, []);

  const { data: gpuDeviceData, isLoading: isGpuDeviceLoading } = useQuery({
    queryKey: [
      'project',
      namespace,
      'workload',
      workloadId,
      'metrics',
      'gpu_device_utilization',
      podName,
      {
        start: timeRange.start.toISOString(),
        end: timeRange.end.toISOString(),
      },
    ],
    queryFn: () =>
      getTimeseriesMetric({
        workloadId,
        namespace: namespace!,
        start: timeRange.start,
        end: timeRange.end,
        metric: 'gpu_device_utilization',
        podName: podName,
      }),
    enabled: !!namespace,
  });

  const { data: gpuMemoryData, isLoading: isGpuMemoryLoading } = useQuery({
    queryKey: [
      'project',
      namespace,
      'workload',
      workloadId,
      'metrics',
      'gpu_memory_utilization',
      podName,
      {
        start: timeRange.start.toISOString(),
        end: timeRange.end.toISOString(),
      },
    ],
    queryFn: () =>
      getTimeseriesMetric({
        workloadId,
        namespace: namespace!,
        start: timeRange.start,
        end: timeRange.end,
        metric: 'gpu_memory_utilization',
        podName: podName,
      }),
    enabled: !!namespace,
  });

  const gpuDeviceChartData = useMemo(() => {
    const values = (gpuDeviceData?.data?.[0]?.values ?? []).map((point) => ({
      timestamp: point.timestamp,
      value: point.value ?? null,
    }));
    return { numerator: values, denominator: [] };
  }, [gpuDeviceData]);

  const gpuMemoryChartData = useMemo(() => {
    const values = (gpuMemoryData?.data?.[0]?.values ?? []).map((point) => ({
      timestamp: point.timestamp,
      value: point.value ?? null,
    }));
    return { numerator: values, denominator: [] };
  }, [gpuMemoryData]);

  const { data: cpuUsageData, isLoading: isCpuUsageLoading } = useQuery({
    queryKey: [
      'project',
      namespace,
      'workload',
      workloadId,
      'metrics',
      'cpu_usage',
      podName,
      {
        start: timeRange.start.toISOString(),
        end: timeRange.end.toISOString(),
      },
    ],
    queryFn: () =>
      getTimeseriesMetric({
        workloadId,
        namespace: namespace!,
        start: timeRange.start,
        end: timeRange.end,
        metric: 'cpu_usage',
        podName: podName,
      }),
    enabled: !!namespace,
  });

  const { data: systemMemoryData, isLoading: isSystemMemoryLoading } = useQuery(
    {
      queryKey: [
        'project',
        namespace,
        'workload',
        workloadId,
        'metrics',
        'system_memory_usage',
        podName,
        {
          start: timeRange.start.toISOString(),
          end: timeRange.end.toISOString(),
        },
      ],
      queryFn: () =>
        getTimeseriesMetric({
          workloadId,
          namespace: namespace!,
          start: timeRange.start,
          end: timeRange.end,
          metric: 'system_memory_usage',
          podName: podName,
        }),
      enabled: !!namespace,
    },
  );

  const cpuUsageChartData = useMemo(() => {
    const series = cpuUsageData?.data ?? [];
    const used = series.find((s) => s.metadata?.label === 'cpu_usage');
    const allocated = series.find((s) => s.metadata?.label === 'cpu_available');
    return {
      numerator: (used?.values ?? []).map((point) => ({
        timestamp: point.timestamp,
        value: point.value ?? null,
      })),
      denominator: (allocated?.values ?? []).map((point) => ({
        timestamp: point.timestamp,
        value: point.value ?? null,
      })),
    };
  }, [cpuUsageData]);

  const systemMemoryChartData = useMemo(() => {
    const series = systemMemoryData?.data ?? [];
    const used = series.find(
      (s) => s.metadata?.label === 'system_memory_usage',
    );
    const allocated = series.find(
      (s) => s.metadata?.label === 'system_memory_available',
    );
    return {
      numerator: (used?.values ?? []).map((point) => ({
        timestamp: point.timestamp,
        value: point.value ?? null,
      })),
      denominator: (allocated?.values ?? []).map((point) => ({
        timestamp: point.timestamp,
        value: point.value ?? null,
      })),
    };
  }, [systemMemoryData]);

  if (!namespace) return null;

  return (
    <>
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">
          {t('details.sections.inferenceMetrics')}
        </h3>
        <ChartTimeSelector
          onTimeRangeChange={handleTimeBoundChange}
          initialTimePeriod={TimeRangePeriod['15M']}
          translationPrefix="timeRange"
          onChartsRefresh={handleChartsRefresh}
          isFetching={isFetchingMetrics}
          lastFetchedTimestamp={metricsLastFetchedAt.current}
          periods={[
            TimeRangePeriod['15M'],
            TimeRangePeriod['30M'],
            TimeRangePeriod['1H'],
            TimeRangePeriod['24H'],
            TimeRangePeriod['7D'],
          ]}
        />
      </div>
      <div className="flex flex-col gap-4 w-full">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 w-full [&>div]:min-w-0">
          {LATENCY_METRICS.map((config) => (
            <div key={config.metric} className="min-w-0">
              <TimeseriesMetricCard
                config={config}
                namespace={namespace}
                workloadId={workloadId}
                timeRange={timeRange}
                podName={podName}
              />
            </div>
          ))}
          <div className="min-w-0">
            <GPUDeviceUsageCard
              data={gpuDeviceChartData}
              isLoading={isGpuDeviceLoading}
              width={280}
            />
          </div>
          <div className="min-w-0">
            <GPUMemoryUsageCard
              data={gpuMemoryChartData}
              isLoading={isGpuMemoryLoading}
              width={280}
            />
          </div>
          <div className="min-w-0">
            <CPUCoreUsageCard
              data={cpuUsageChartData}
              isLoading={isCpuUsageLoading}
              width={280}
            />
          </div>
          <div className="min-w-0">
            <SystemMemoryUsageCard
              data={systemMemoryChartData}
              isLoading={isSystemMemoryLoading}
              width={280}
            />
          </div>
        </div>
        <div className="flex flex-col lg:flex-row gap-3 w-full">
          <div className="min-w-0 flex-1">
            <InferenceRequestsCard
              namespace={namespace}
              workloadId={workloadId}
              timeRange={timeRange}
              timePeriod={currentTimePeriod.current}
              podName={podName}
            />
          </div>
          <div className="grid grid-cols-2 grid-rows-3 gap-2 w-full lg:w-[280px] shrink-0">
            {SCALAR_METRICS.map((config) => (
              <ScalarMetricCard
                key={config.metric}
                config={config}
                namespace={namespace}
                workloadId={workloadId}
                timeRange={timeRange}
                podName={podName}
              />
            ))}
          </div>
        </div>
      </div>
    </>
  );
};

export default InferenceMetrics;
