// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useProject } from '@/contexts/ProjectContext';

import type {
  TimeRangePeriod,
  TimeSeriesAllocationData,
} from '@amdenterpriseai/types';

import { getCurrentTimeRange } from '@amdenterpriseai/utils/app';
import { getTimeseriesMetric } from '@/lib/app/metrics';
import type { components } from '@/types/api';

interface WorkloadMetricsParams {
  workloadId: string;
  namespace: string;
  timePeriod: TimeRangePeriod;
  metricName: components['schemas']['MetricName'];
}

interface DashboardMetricsParams {
  data: TimeSeriesAllocationData;
}

type MetricsParams =
  | { type: 'workload'; params: WorkloadMetricsParams }
  | { type: 'dashboard'; params: DashboardMetricsParams };

interface UseGPUMetricsResult {
  chartData: TimeSeriesAllocationData;
  isLoading: boolean;
}

/**
 * Custom hook for fetching and transforming GPU metrics data.
 * Handles both dashboard (static data) and workload (fetched data) modes.
 *
 * @param config - Metrics configuration (workload or dashboard mode)
 * @param isLoadingProp - Optional external loading state (for dashboard mode)
 * @returns Chart data and loading state
 */
export function useGPUMetrics(
  config: MetricsParams,
  isLoadingProp?: boolean,
): UseGPUMetricsResult {
  const { activeProject } = useProject();
  const isWorkload = config.type === 'workload';

  // Only fetch when in workload mode
  const { data: workloadData, isLoading: workloadLoading } = useQuery({
    queryKey: [
      'project',
      activeProject,
      'workload',
      isWorkload ? config.params.workloadId : '',
      'metrics',
      isWorkload ? config.params.metricName : '',
      isWorkload ? config.params.timePeriod : '',
    ],
    queryFn: () => {
      if (!isWorkload) {
        throw new Error('Query should not run in dashboard mode');
      }

      const { workloadId, namespace, timePeriod, metricName } = config.params;
      const { start, end } = getCurrentTimeRange(timePeriod);

      return getTimeseriesMetric({
        workloadId,
        namespace,
        start,
        end,
        metric: metricName,
      });
    },
    enabled: isWorkload,
  });

  // Transform data based on mode
  const chartData: TimeSeriesAllocationData = useMemo(() => {
    if (isWorkload) {
      const values = (workloadData?.data?.[0]?.values ?? []).map((point) => ({
        timestamp: point.timestamp,
        value: point.value ?? null,
      }));
      return { numerator: values, denominator: [] };
    }
    return config.params.data;
  }, [isWorkload, workloadData, config.params]);

  const isLoading = isWorkload ? workloadLoading : (isLoadingProp ?? false);

  return { chartData, isLoading };
}
