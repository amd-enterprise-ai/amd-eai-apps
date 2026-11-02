// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { components } from '@/types/api';

/**
 * Wire shape returned by the workloads endpoints, aliased from the generated
 * OpenAPI schema so drift against the backend contract fails `pnpm typecheck`.
 * Use this where only fields the backend actually returns are needed.
 */
export type Workload = components['schemas']['WorkloadResponse'];

export type LogEntry = components['schemas']['LogEntry'];

// Display-status superset for badge rendering and resource metrics. The FE
// synthesizes Degraded from AIM service health.
export type ResourceStatus =
  | components['schemas']['WorkloadStatus']
  | 'Degraded';

export type LogLevel = components['schemas']['LogLevel'];
