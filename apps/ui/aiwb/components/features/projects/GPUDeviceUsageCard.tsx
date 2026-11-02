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

const GPU_DEVICE_CONFIG = {
  metricName: 'gpu_device_utilization',
  chartColor: 'fuchsia',
  titleKey: 'dashboard.overview.gpuDeviceUsage.title',
  tooltipKey: 'dashboard.overview.gpuDeviceUsage.description',
  upperLimitUnallocatedKey:
    'dashboard.overview.gpuDeviceUsage.upperLimitUnallocated',
  upperLimitKey: 'dashboard.overview.gpuDeviceUsage.upperLimit',
  upperLimitAvailableKey:
    'dashboard.overview.gpuDeviceUsage.upperLimitAvailable',
  dataFormatter: (value: number | null) => Number(value).toFixed(0),
} as const satisfies GPUUsageCardConfig;

export const GPUDeviceUsageCard: React.FC<Props> = (props) => {
  return <BaseGPUUsageCard {...props} config={GPU_DEVICE_CONFIG} />;
};

export default GPUDeviceUsageCard;
