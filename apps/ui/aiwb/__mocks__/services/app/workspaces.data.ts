// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { WorkspaceCatalogItem } from '@/types/workspaces';

export const mockWorkspaceCatalogItems: WorkspaceCatalogItem[] = [
  {
    id: '1',
    name: 'test-workload-1',
    displayName: 'Test workload 1',
    slug: 'test-workload-1',
    description: 'Test description 1',
    longDescription: 'Detailed description for Test workload 1',
    type: 'WORKSPACE',
    category: 'development',
    createdAt: '2023-01-01T00:00:00Z',
    updatedAt: '2023-01-01T00:00:00Z',
    createdBy: null,
    updatedBy: null,
    tags: ['tag1', 'tag2'],
    featuredImage: '',
    requiredResources: {
      gpuCount: 1,
      gpuMemory: 8,
      cpuCoreCount: 4,
      systemMemory: 16,
    },
    externalUrl: 'https://example.com/workload-1',
    usageScope: 'user',
  },
  {
    id: '2',
    name: 'test-workload-2',
    displayName: 'Test workload 2',
    slug: 'test-workload-2',
    description: 'Test description 2',
    longDescription: 'Detailed description for Test workload 2',
    type: 'WORKSPACE',
    category: 'development',
    createdAt: '2023-01-02T00:00:00Z',
    updatedAt: '2023-01-02T00:00:00Z',
    createdBy: null,
    updatedBy: null,
    tags: ['tag3'],
    featuredImage: '',
    requiredResources: {
      gpuCount: 2,
      gpuMemory: 16,
      cpuCoreCount: 8,
      systemMemory: 32,
    },
    externalUrl: 'https://example.com/workload-2',
    usageScope: 'user',
  },
];

export const mockProjectScopedWorkspaceCatalogItems: WorkspaceCatalogItem[] = [
  {
    displayName: 'MLflow Tracking Server',
    slug: 'mlflow',
    description: 'ML experiment tracking and model management',
    longDescription:
      'MLflow is an open-source platform for managing the machine learning lifecycle, including experimentation, reproducibility, deployment, and a central model registry. This deployment provides a centralized MLflow tracking server for logging metrics, parameters, and artifacts from machine learning experiments.',
    category: 'development',
    tags: ['mlflow', 'experiment-tracking', 'model-management'],
    featuredImage: 'https://avatars.githubusercontent.com/u/39938107',
    requiredResources: {
      gpuCount: 0,
      gpuMemory: 0,
      cpuCoreCount: 1,
      systemMemory: 20,
    },
    externalUrl: 'https://mlflow.org/',
    name: 'dev-tracking-mlflow',
    type: 'WORKSPACE',
    id: '28d2eee1-616e-47ae-a73d-19c72a939d27',
    createdAt: '2025-09-24T09:53:26.239368Z',
    updatedAt: '2025-09-24T09:53:26.239368Z',
    createdBy: null,
    updatedBy: null,
    usageScope: 'namespace',
  },
];
