// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { PaginationMetadata } from './pagination';
import { WorkloadStatus } from './enums/workloads';

import { WorkloadType } from '@amdenterpriseai/types';

export type ProjectUtilization = {
  date: string;
  memoryUsage: number;
  deviceUsage: number;
};

export interface Workload {
  id: string;
  type: WorkloadType | null;
  displayName: string;
  createdBy: string;
  createdAt: string;
  updatedAt: string;
  updatedBy?: string | null;
  status: WorkloadStatus;
  projectId: string;
  clusterId: string;
}

export type WorkloadsStats = {
  runningWorkloadsCount: number;
  pendingWorkloadsCount: number;
};

export interface WorkloadFilterItem {
  key: string;
  label: string;
  showDivider?: boolean;
}

export type WorkloadWithMetrics = Workload & {
  gpuCount: number;
  vram: number;
  runTime?: number;
};

export type ProjectWorkloadsMetricsResponse = {
  data: WorkloadWithMetrics[];
  pagination: PaginationMetadata;
};

export type ClusterWorkloadsMetricsResponse = {
  data: WorkloadWithMetrics[];
  pagination: PaginationMetadata;
};

export type GpuDeviceInfo = {
  gpuId: string;
  hostname: string;
};

export type NodeWorkloadWithMetrics = {
  id: string;
  projectId: string;
  clusterId: string;
  status: WorkloadStatus;
  displayName: string | null;
  type: WorkloadType | null;
  gpuCount: number;
  vram: number;
  gpuDevices: GpuDeviceInfo[];
  createdAt: string;
  createdBy: string;
};

export type NodeWorkloadsMetricsResponse = {
  data: NodeWorkloadWithMetrics[];
};

export type WorkloadResponse = Workload & {
  projectId?: string;
  clusterId?: string;
};

export type WorkloadMetricsDetails = {
  name: string | null;
  id: string;
  createdBy: string | null;
  clusterName: string | null;
  clusterId: string;
  nodesInUse: number;
  gpuDevicesInUse: number;
  createdAt: string;
  updatedAt: string;
  queueTime: number;
  runningTime: number;
};

export type GpuDeviceMetricValue = {
  value: number;
  timestamp: string;
};

export type GpuDeviceMetricResponse = {
  gpuUuid: string;
  gpuId: string;
  hostname: string;
  metric: {
    seriesLabel: string;
    values: GpuDeviceMetricValue[];
  };
};

export type WorkloadGpuDevicesMetricsResponse = {
  gpuDevices: GpuDeviceMetricResponse[];
  range: { start: string; end: string };
};

/** Merged per-device snapshot used by the workload detail page for charting. */
export type WorkloadGpuDeviceSnapshot = {
  gpuUuid: string;
  gpuId: string;
  hostname: string;
  displayLabel?: string;
  vramUtilizationPct: number | null;
  gpuUtilizationPct: number | null;
  powerUsageW: number | null;
  vramUtilizationSeries?: { time: string; value: number }[];
  gpuUtilizationSeries?: { time: string; value: number }[];
  powerUsageSeries?: { time: string; value: number }[];
};
