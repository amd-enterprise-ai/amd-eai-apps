// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { ResourceStatus } from '@/types/workloads';
import type { components } from '@/types/api';
import type { ModelProfileSummaryFields } from '@/types/aims';

export type ProjectsResponse =
  components['schemas']['ListResponse_ProjectResponse_'];

// Schema WorkloadMetrics plus the AIMProfile-catalog fields joined client-side.
export type EnrichedWorkloadMetrics = Omit<
  components['schemas']['WorkloadMetrics'],
  'status'
> & {
  // The aim detail page synthesizes a row from an AIMService whose status can be
  // Degraded, which the wire WorkloadStatus union omits; widen to ResourceStatus
  // so both the schema-sourced rows and that row fit without a cast.
  status: ResourceStatus;
} & ModelProfileSummaryFields;
