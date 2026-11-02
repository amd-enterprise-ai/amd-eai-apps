// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { displayHumanReadableMegaBytes } from '@amdenterpriseai/utils/app';
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

const GPU_MEMORY_CONFIG = {
  metricName: 'gpu_memory_utilization',
  chartColor: 'cyan',
  titleKey: 'dashboard.overview.vramDeviceUsage.title',
  tooltipKey: 'dashboard.overview.vramDeviceUsage.description',
  upperLimitUnallocatedKey:
    'dashboard.overview.vramDeviceUsage.upperLimitUnallocated',
  upperLimitKey: 'dashboard.overview.vramDeviceUsage.upperLimit',
  upperLimitAvailableKey:
    'dashboard.overview.vramDeviceUsage.upperLimitAvailable',
  dataFormatter: (value: number | null) =>
    displayHumanReadableMegaBytes(Number(value)),
} as const satisfies GPUUsageCardConfig;

export const GPUMemoryUsageCard: React.FC<Props> = (props) => {
  return <BaseGPUUsageCard {...props} config={GPU_MEMORY_CONFIG} />;
};

export default GPUMemoryUsageCard;
