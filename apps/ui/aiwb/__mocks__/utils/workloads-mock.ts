// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { Workload } from '@/types/workloads';

import { v4 as uuidv4 } from 'uuid';

export const generateMockWorkspaceWorkloads = (
  n: number,
  name: string,
  status: Workload['status'],
  type: Workload['type'],
): Workload[] => {
  const template = {
    id: '',
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    createdBy: 'user@example.com',
    updatedBy: null,
    namespace: 'test-namespace',
    description: null,
    endpoints: {},
    displayName: '',
    name: '',
    status,
    type,
    chartId: null,
    datasetId: null,
  };

  const workloads = Array.from({ length: n }, () => {
    const workloadId = uuidv4();

    return {
      ...template,
      id: workloadId,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      displayName: `${name}-${new Date()
        .toISOString()
        .replace(/[-:.TZ]/g, '')
        .slice(0, 14)}`,
      name: `mw-dev-tracking-${name}-${Math.floor(Math.random() * 1000000000)}-${workloadId.slice(0, 4)}`,
      status,
      type,
    };
  });

  return workloads;
};
