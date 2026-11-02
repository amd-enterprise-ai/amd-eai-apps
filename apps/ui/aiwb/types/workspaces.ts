// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT
import type { components } from '@/types/api';

export type WorkspaceCatalogItem = components['schemas']['ChartListResponse'];

/**
 * Catalog item decorated with the workspace deployment state the workspaces
 * page joins in client-side. These fields are NOT part of the backend catalog
 * response — they are derived from a separate workloads fetch, so they live on
 * the view-model rather than the API-backed WorkspaceCatalogItem.
 */
export type WorkspaceCatalogTableItem =
  components['schemas']['ChartListResponse'] & {
    available?: boolean;
    workloads?: components['schemas']['WorkloadResponse'][];
    workloadsCount?: number;
    status?: components['schemas']['WorkloadStatus'];
    outputs?: string[];
  };

export type WorkspaceDeploymentPayload = {
  type: 'workspaces';
  template: components['schemas']['WorkspaceType'];
  // Used for deployment payload
  displayName?: string;
  gpus: number;
  memoryPerGpu: number;
  cpuPerGpu: number;
  image?: string;
  imagePullSecrets?: string[];
  replicas?: number;
};
