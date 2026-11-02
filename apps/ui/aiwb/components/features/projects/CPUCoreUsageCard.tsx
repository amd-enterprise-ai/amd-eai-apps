// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { BaseGPUUsageCard, type GPUUsageCardConfig } from './BaseGPUUsageCard';

import type {
  TimeRangePeriod,
  TimeSeriesAllocationData,
} from '@amdenterpriseai/types';

type DashboardProps = {
  data: TimeSeriesAllocationData;
  isLoading?: boolean;
  width?: number;
  fillHeight?: boolean;
  alertTooltip?: string;
  hasDedicatedQuota?: boolean;
  workloadId?: never;
  namespace?: never;
  timePeriod?: never;
};

type WorkloadProps = {
  data?: never;
  workloadId: string;
  namespace: string;
  timePeriod: TimeRangePeriod;
  isLoading?: boolean;
  width?: number;
  alertTooltip?: string;
  hasDedicatedQuota?: boolean;
};

type Props = DashboardProps | WorkloadProps;

const CPU_CORE_CONFIG = {
  metricName: 'cpu_usage',
  chartColor: 'green',
  titleKey: 'dashboard.overview.cpuCoreUsage.title',
  tooltipKey: 'dashboard.overview.cpuCoreUsage.description',
  upperLimitUnallocatedKey:
    'dashboard.overview.cpuCoreUsage.upperLimitUnallocated',
  upperLimitKey: 'dashboard.overview.cpuCoreUsage.upperLimit',
  upperLimitAvailableKey: 'dashboard.overview.cpuCoreUsage.upperLimitAvailable',
  dataFormatter: (value: number | null) => Number(value).toFixed(1),
} as const satisfies GPUUsageCardConfig;

export const CPUCoreUsageCard: React.FC<Props> = (props) => {
  return <BaseGPUUsageCard {...props} config={CPU_CORE_CONFIG} />;
};

export default CPUCoreUsageCard;
