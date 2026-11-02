// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useMemo } from 'react';

import { useTranslation } from 'next-i18next';

import { StatisticsCard } from '@amdenterpriseai/components';
import { TimeRange } from '@amdenterpriseai/types';
import type { components } from '@/types/api';
import { getScalarMetric } from '@/lib/app/metrics';
import { useQuery } from '@tanstack/react-query';
import { useProject } from '@/contexts/ProjectContext';
import {
  MetricLocaleKey,
  METRIC_TITLE_KEYS,
  METRIC_DESCRIPTION_KEYS,
} from './TimeseriesMetricCard';

export interface ScalarMetricConfig {
  /** Backend metric slug (e.g. 'max_requests') */
  metric: components['schemas']['MetricName'];
  /** Locale key under details.metrics (e.g. 'maxRequests') */
  localeKey: MetricLocaleKey;
  /** Transform raw scalar before display (default: Math.round) */
  transform?: (value: number) => number;
  /** Optional display formatter passed to StatisticsCard */
  formatter?: (value: number) => string;
}

interface Props {
  config: ScalarMetricConfig;
  namespace: string;
  workloadId: string;
  timeRange: TimeRange;
  podName?: string;
}

const defaultTransform = (v: number) => Math.round(v);

export const ScalarMetricCard: React.FC<Props> = ({
  config,
  namespace,
  workloadId,
  timeRange,
  podName,
}) => {
  const { t } = useTranslation('workloads');
  const { activeProject } = useProject();
  const { metric, localeKey, transform = defaultTransform, formatter } = config;

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
      getScalarMetric({
        workloadId,
        namespace,
        start: timeRange.start,
        end: timeRange.end,
        metric,
        podName,
      }),
  });

  const statistic = useMemo(
    () => transform(data?.data ?? 0),
    [data, transform],
  );

  return (
    <StatisticsCard
      title={t(METRIC_TITLE_KEYS[localeKey])}
      tooltip={t(METRIC_DESCRIPTION_KEYS[localeKey])}
      statistic={statistic}
      statisticFormatter={formatter}
      isLoading={isLoading}
      compact
    />
  );
};

export default ScalarMetricCard;
