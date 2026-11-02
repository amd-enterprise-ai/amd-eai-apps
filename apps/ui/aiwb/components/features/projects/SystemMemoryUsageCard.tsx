// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { displayHumanReadableBytes } from '@amdenterpriseai/utils/app';
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

const SYSTEM_MEMORY_CONFIG = {
  metricName: 'system_memory_usage',
  chartColor: 'amber',
  titleKey: 'dashboard.overview.systemMemoryUsage.title',
  tooltipKey: 'dashboard.overview.systemMemoryUsage.description',
  upperLimitUnallocatedKey:
    'dashboard.overview.systemMemoryUsage.upperLimitUnallocated',
  upperLimitKey: 'dashboard.overview.systemMemoryUsage.upperLimit',
  upperLimitAvailableKey:
    'dashboard.overview.systemMemoryUsage.upperLimitAvailable',
  // kubeletstats working-set is in bytes (unlike GPU VRAM which is in MB).
  dataFormatter: (value: number | null) =>
    displayHumanReadableBytes(Number(value)),
} as const satisfies GPUUsageCardConfig;

export const SystemMemoryUsageCard: React.FC<Props> = (props) => {
  return <BaseGPUUsageCard {...props} config={SYSTEM_MEMORY_CONFIG} />;
};

export default SystemMemoryUsageCard;
