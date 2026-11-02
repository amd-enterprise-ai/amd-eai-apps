// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useMemo } from 'react';

import { useTranslation } from 'next-i18next';

import { StatsWithLineChart } from '@amdenterpriseai/components';
import {
  AvailableChartColorsKeys,
  TimeRange,
  TimeSeriesData,
} from '@amdenterpriseai/types';
import { getTimeseriesMetric } from '@/lib/app/metrics';
import { useQuery } from '@tanstack/react-query';
import { useProject } from '@/contexts/ProjectContext';
import type { workloadsKeys } from '@/types/react-i18next';
import type { components } from '@/types/api';

export type MetricLocaleKey =
  | 'timeToFirstToken'
  | 'interTokenLatency'
  | 'endToEndLatency'
  | 'inferenceRequests'
  | 'maxRequests'
  | 'minRequests'
  | 'avgRequests'
  | 'totalRequests'
  | 'totalTokens'
  | 'kvCacheUsage'
  | 'gpuConsumption'
  | 'vram';

export const METRIC_TITLE_KEYS = {
  timeToFirstToken: 'details.metrics.timeToFirstToken.title',
  interTokenLatency: 'details.metrics.interTokenLatency.title',
  endToEndLatency: 'details.metrics.endToEndLatency.title',
  inferenceRequests: 'details.metrics.inferenceRequests.title',
  maxRequests: 'details.metrics.maxRequests.title',
  minRequests: 'details.metrics.minRequests.title',
  avgRequests: 'details.metrics.avgRequests.title',
  totalRequests: 'details.metrics.totalRequests.title',
  totalTokens: 'details.metrics.totalTokens.title',
  kvCacheUsage: 'details.metrics.kvCacheUsage.title',
  gpuConsumption: 'details.metrics.gpuConsumption.title',
  vram: 'details.metrics.vram.title',
} as const satisfies Record<MetricLocaleKey, workloadsKeys>;

export const METRIC_DESCRIPTION_KEYS = {
  timeToFirstToken: 'details.metrics.timeToFirstToken.description',
  interTokenLatency: 'details.metrics.interTokenLatency.description',
  endToEndLatency: 'details.metrics.endToEndLatency.description',
  inferenceRequests: 'details.metrics.inferenceRequests.description',
  maxRequests: 'details.metrics.maxRequests.description',
  minRequests: 'details.metrics.minRequests.description',
  avgRequests: 'details.metrics.avgRequests.description',
  totalRequests: 'details.metrics.totalRequests.description',
  totalTokens: 'details.metrics.totalTokens.description',
  kvCacheUsage: 'details.metrics.kvCacheUsage.description',
  gpuConsumption: 'details.metrics.gpuConsumption.description',
  vram: 'details.metrics.vram.description',
} as const satisfies Record<MetricLocaleKey, workloadsKeys>;

export interface TimeseriesMetricConfig {
  /** Backend metric slug (e.g. 'time_to_first_token_seconds') */
  metric: components['schemas']['MetricName'];
  /** Locale key under details.metrics (e.g. 'timeToFirstToken') */
  localeKey: MetricLocaleKey;
  /** Chart line color */
  color: AvailableChartColorsKeys;
  /** Value formatter for the chart tooltip/stat */
  dataFormatter?: (value: number | string) => string;
}

interface Props {
  config: TimeseriesMetricConfig;
  namespace: string;
  workloadId: string;
  timeRange: TimeRange;
  podName?: string;
  width?: number;
}

export const TimeseriesMetricCard: React.FC<Props> = ({
  config,
  namespace,
  workloadId,
  timeRange,
  podName,
  width = 460,
}) => {
  const { t } = useTranslation('workloads');
  const { activeProject } = useProject();
  const { metric, localeKey, color, dataFormatter } = config;

  const { data, isLoading } = useQuery({
    queryKey: [
      'project',
      activeProject,
      'workload',
      workloadId,
      'metrics',
      metric,
      podName,
      {
        start: timeRange.start.toISOString(),
        end: timeRange.end.toISOString(),
      },
    ],
    queryFn: () =>
      getTimeseriesMetric({
        workloadId,
        namespace,
        start: timeRange.start,
        end: timeRange.end,
        metric,
        podName,
      }),
  });

  const chartData: TimeSeriesData = useMemo(() => {
    if (!data?.data) return { values: [], timestamps: [], metadata: {} };

    return {
      metadata: data.data[0]?.metadata || {},
      values: (data.data[0]?.values ?? []).map((point) => ({
        timestamp: point.timestamp,
        value: point.value ?? null,
      })),
      timestamps: data.range.timestamps || [],
    };
  }, [data]);

  return (
    <StatsWithLineChart
      title={t(METRIC_TITLE_KEYS[localeKey])}
      tooltip={t(METRIC_DESCRIPTION_KEYS[localeKey])}
      data={chartData.values}
      dataFormatter={dataFormatter}
      width={width}
      colors={[color]}
      isLoading={isLoading}
    />
  );
};

export default TimeseriesMetricCard;
