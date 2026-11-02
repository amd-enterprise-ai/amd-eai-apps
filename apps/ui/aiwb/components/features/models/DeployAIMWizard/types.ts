// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  AIM_PROFILE_TYPE_OPTIMIZED,
  type AIMClusterProfile,
} from '@/types/aims';

export type DeployAIMFormValues = {
  model: string;
  displayName?: string;
  hfTokenSecretName?: string;
  /** Comma-joined while editing (FormSelect multi-select); an array once parsed. */
  imagePullSecrets?: string | string[];
  personalizationEnabled?: boolean;
  adapters?: string[];
  maxLoraRank?: string;
  performanceMode: PerformanceMode;
  autoscalingEnabled: boolean;
  minReplicas?: number;
  maxReplicas?: number;
  metricQuery?: string;
  operationOverTime?: string;
  targetType?: string;
  targetValue?: number;
  optimizationClass?: string;
  gpuModel?: string;
  precision?: string;
  gpuCount?: string;
  profileName?: string;
};

export type AdvancedProfileOptions = {
  optimizationClasses: string[];
  gpuModels: string[];
  precisions: string[];
  gpuCounts: string[];
  profiles: AIMClusterProfile[];
};

export const PERFORMANCE_MODE_ADVANCED = 'advanced';

export type PerformanceMode =
  | 'latency'
  | 'throughput'
  | typeof PERFORMANCE_MODE_ADVANCED;

export function getMetricsStatusMap(
  readyProfiles: AIMClusterProfile[],
): Record<string, boolean> {
  const result: Record<string, boolean> = {};
  for (const profile of readyProfiles) {
    const metric = profile.spec?.metric;
    if (metric == null) continue;
    const metricKey = String(metric);
    const isOptimized = profile.spec?.type === AIM_PROFILE_TYPE_OPTIMIZED;
    result[metricKey] = result[metricKey] || isOptimized;
  }
  return result;
}
