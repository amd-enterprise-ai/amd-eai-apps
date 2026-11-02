// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { afterEach, beforeEach, describe, expect, it, Mock, vi } from 'vitest';

import {
  attachAdapterToDeployment,
  deleteInferenceDeployment,
  deployInference,
  getInferenceDeployment,
  getInferenceModel,
  invalidateAdapterQueries,
  listAllInferenceDeployments,
  listAllInferenceModels,
  listInferenceDeployments,
  listInferenceModels,
  updateInferenceAdapters,
  updateInferenceScaling,
} from '@/lib/app/inference';
import { AIMDeployPayload, type AIMService } from '@/types/aims';
import { apiClient } from '@/lib/api-client';

vi.mock('@/lib/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api-client')>();
  return {
    ...actual,
    apiClient: { GET: vi.fn(), POST: vi.fn(), PATCH: vi.fn(), DELETE: vi.fn() },
  };
});

const mockGet = apiClient.GET as Mock;
const mockPost = apiClient.POST as Mock;
const mockPatch = apiClient.PATCH as Mock;
const mockDelete = apiClient.DELETE as Mock;

afterEach(() => {
  mockGet.mockReset();
  mockPost.mockReset();
  mockPatch.mockReset();
  mockDelete.mockReset();
});

const success = (data: unknown) => ({
  data,
  error: undefined,
  response: { ok: true, status: 200 },
});
const failure = (status: number) => ({
  data: undefined,
  error: { detail: 'boom' },
  response: { ok: false, status, statusText: 'Error' },
});

describe('invalidateAdapterQueries', () => {
  it('refreshes every inference query in the project', async () => {
    const invalidateQueries = vi.fn();

    await invalidateAdapterQueries({ invalidateQueries } as never, 'project-1');

    expect(invalidateQueries).toHaveBeenCalledWith({
      queryKey: ['project', 'project-1', 'inference'],
    });
  });

  it('refreshes the deployment details query in the project', async () => {
    const invalidateQueries = vi.fn();

    await invalidateAdapterQueries({ invalidateQueries } as never, 'project-1');

    expect(invalidateQueries).toHaveBeenCalledWith({
      queryKey: ['aimService', 'project-1'],
    });
  });
});

describe('getInferenceModel', () => {
  it('GETs a single model by name', async () => {
    mockGet.mockResolvedValueOnce(
      success({ metadata: { name: 'aim-llama/3' } }),
    );

    await getInferenceModel('aim-llama/3');

    expect(mockGet).toHaveBeenCalledWith('/api/inference/models/{name}', {
      params: { path: { name: 'aim-llama/3' } },
    });
  });

  it('rejects when name is empty', async () => {
    await expect(getInferenceModel('')).rejects.toThrow(
      /No inference model name/,
    );
  });
});

describe('listInferenceModels', () => {
  it('GETs inference models with default pagination', async () => {
    mockGet.mockResolvedValueOnce(
      success({
        data: [{ metadata: { name: 'm1' } }],
        pagination: { page: 1, pageSize: 10, total: 1 },
      }),
    );

    await listInferenceModels();

    expect(mockGet).toHaveBeenCalledWith('/api/inference/models', {
      params: {
        query: { page: 1, pageSize: 10, statusFilter: undefined },
      },
    });
  });

  it('forwards explicit page and pageSize', async () => {
    mockGet.mockResolvedValueOnce(
      success({
        data: [],
        pagination: { page: 2, pageSize: 25, total: 50 },
      }),
    );

    await listInferenceModels({ page: 2, pageSize: 25 });

    expect(mockGet).toHaveBeenCalledWith('/api/inference/models', {
      params: {
        query: { page: 2, pageSize: 25, statusFilter: undefined },
      },
    });
  });

  it('forwards statusFilter as an array', async () => {
    mockGet.mockResolvedValueOnce(
      success({ data: [], pagination: { page: 1, pageSize: 10, total: 0 } }),
    );

    await listInferenceModels({
      statusFilter: ['Ready', 'Failed'],
    });

    expect(mockGet).toHaveBeenCalledWith('/api/inference/models', {
      params: {
        query: {
          page: 1,
          pageSize: 10,
          statusFilter: ['Ready', 'Failed'],
        },
      },
    });
  });

  it('returns the paginated envelope verbatim', async () => {
    const envelope = {
      data: [{ metadata: { name: 'm1' } }],
      pagination: { page: 1, pageSize: 10, total: 1 },
    };
    mockGet.mockResolvedValueOnce(success(envelope));

    const result = await listInferenceModels();

    expect(result).toEqual(envelope);
  });

  it('throws APIRequestError when the typed client returns an error', async () => {
    mockGet.mockResolvedValueOnce(failure(500));

    await expect(listInferenceModels()).rejects.toThrow(
      /Failed to fetch inference models/,
    );
  });
});

describe('listAllInferenceModels', () => {
  it('GETs inference models with pageSize=100 on the first page', async () => {
    mockGet.mockResolvedValueOnce(
      success({
        data: [],
        pagination: { page: 1, pageSize: 100, total: 0 },
      }),
    );

    await listAllInferenceModels();

    expect(mockGet).toHaveBeenCalledWith('/api/inference/models', {
      params: {
        query: { page: 1, pageSize: 100, statusFilter: undefined },
      },
    });
  });

  it('forwards statusFilter as an array', async () => {
    mockGet.mockResolvedValueOnce(
      success({
        data: [],
        pagination: { page: 1, pageSize: 100, total: 0 },
      }),
    );

    await listAllInferenceModels(['Ready', 'Failed']);

    expect(mockGet).toHaveBeenCalledWith('/api/inference/models', {
      params: {
        query: {
          page: 1,
          pageSize: 100,
          statusFilter: ['Ready', 'Failed'],
        },
      },
    });
  });

  it('unwraps the paginated envelope to AIMClusterModel[] for a single page', async () => {
    mockGet.mockResolvedValueOnce(
      success({
        data: [{ metadata: { name: 'm1' } }, { metadata: { name: 'm2' } }],
        pagination: { page: 1, pageSize: 100, total: 2 },
      }),
    );

    const result = await listAllInferenceModels();

    expect(result).toEqual([
      { metadata: { name: 'm1' } },
      { metadata: { name: 'm2' } },
    ]);
  });

  it('walks subsequent pages and concatenates when total exceeds one page', async () => {
    mockGet
      .mockResolvedValueOnce(
        success({
          data: [{ metadata: { name: 'm1' } }],
          pagination: { page: 1, pageSize: 100, total: 250 },
        }),
      )
      .mockResolvedValueOnce(
        success({
          data: [{ metadata: { name: 'm2' } }],
          pagination: { page: 2, pageSize: 100, total: 250 },
        }),
      )
      .mockResolvedValueOnce(
        success({
          data: [{ metadata: { name: 'm3' } }],
          pagination: { page: 3, pageSize: 100, total: 250 },
        }),
      );

    const result = await listAllInferenceModels();

    expect(result).toEqual([
      { metadata: { name: 'm1' } },
      { metadata: { name: 'm2' } },
      { metadata: { name: 'm3' } },
    ]);
    expect(mockGet).toHaveBeenCalledTimes(3);
    expect(mockGet).toHaveBeenNthCalledWith(2, '/api/inference/models', {
      params: {
        query: { page: 2, pageSize: 100, statusFilter: undefined },
      },
    });
    expect(mockGet).toHaveBeenNthCalledWith(3, '/api/inference/models', {
      params: {
        query: { page: 3, pageSize: 100, statusFilter: undefined },
      },
    });
  });

  it('returns [] and does not throw on typed client error (graceful degrade)', async () => {
    mockGet.mockResolvedValueOnce(failure(500));

    const result = await listAllInferenceModels();

    expect(result).toEqual([]);
  });

  it('returns [] when a subsequent page fails (graceful degrade)', async () => {
    mockGet
      .mockResolvedValueOnce(
        success({
          data: [{ metadata: { name: 'm1' } }],
          pagination: { page: 1, pageSize: 100, total: 250 },
        }),
      )
      .mockResolvedValueOnce(failure(500));

    const result = await listAllInferenceModels();

    expect(result).toEqual([]);
  });
});

describe('deployInference', () => {
  it('POSTs the payload with the project path parameter', async () => {
    mockPost.mockResolvedValueOnce(success({ id: 'svc-1' }));

    const payload: AIMDeployPayload = {
      model: 'llama3-8b',
      replicas: 1,
      hfToken: 'my-hf-secret',
      imagePullSecrets: ['s1'],
      minReplicas: 2,
      maxReplicas: 10,
      autoScaling: {
        metrics: [
          {
            type: 'PodMetric',
            podmetric: {
              metric: {
                backend: 'opentelemetry',
                metricNames: ['vllm:num_requests_waiting'],
                query: 'vllm:num_requests_waiting',
                operationOverTime: 'avg',
              },
              target: { type: 'Value', value: '5' },
            },
          },
        ],
      },
    };

    await deployInference('proj-1', payload);

    expect(mockPost).toHaveBeenCalledWith('/api/projects/{project}/inference', {
      params: { path: { project: 'proj-1' } },
      body: payload,
    });
  });

  it('rejects when project is empty', async () => {
    await expect(
      deployInference('', { model: 'm' } as AIMDeployPayload),
    ).rejects.toThrow(/No project selected/);
  });
});

describe('listInferenceDeployments', () => {
  it('GETs the project list endpoint with default pagination', async () => {
    mockGet.mockResolvedValueOnce(
      success({
        data: [],
        pagination: { page: 1, pageSize: 10, total: 0 },
      }),
    );

    await listInferenceDeployments('proj-1');

    expect(mockGet).toHaveBeenCalledWith('/api/projects/{project}/inference', {
      params: {
        path: { project: 'proj-1' },
        query: { page: 1, pageSize: 10 },
      },
    });
  });

  it('forwards explicit page and pageSize', async () => {
    mockGet.mockResolvedValueOnce(
      success({
        data: [],
        pagination: { page: 3, pageSize: 25, total: 80 },
      }),
    );

    await listInferenceDeployments('proj-1', { page: 3, pageSize: 25 });

    expect(mockGet).toHaveBeenCalledWith('/api/projects/{project}/inference', {
      params: {
        path: { project: 'proj-1' },
        query: { page: 3, pageSize: 25 },
      },
    });
  });

  it('forwards statusFilter and capability', async () => {
    mockGet.mockResolvedValueOnce(
      success({
        data: [],
        pagination: { page: 1, pageSize: 10, total: 0 },
      }),
    );

    await listInferenceDeployments('proj-1', {
      capability: 'chat',
      statusFilter: ['Running', 'Pending'],
    });

    expect(mockGet).toHaveBeenCalledWith('/api/projects/{project}/inference', {
      params: {
        path: { project: 'proj-1' },
        query: {
          page: 1,
          pageSize: 10,
          capability: 'chat',
          statusFilter: ['Running', 'Pending'],
        },
      },
    });
  });

  it('returns the paginated envelope verbatim', async () => {
    const envelope = {
      data: [{ id: 'svc-1' }, { id: 'svc-2' }],
      pagination: { page: 1, pageSize: 10, total: 2 },
    };
    mockGet.mockResolvedValueOnce(success(envelope));

    const result = await listInferenceDeployments('proj-1');

    expect(result).toEqual(envelope);
  });

  it('throws APIRequestError when the typed client returns an error', async () => {
    mockGet.mockResolvedValueOnce(failure(500));

    await expect(listInferenceDeployments('proj-1')).rejects.toThrow(
      /Failed to fetch inference deployments/,
    );
  });
});

describe('listAllInferenceDeployments', () => {
  it('GETs the project list endpoint with pageSize=100 on the first page', async () => {
    mockGet.mockResolvedValueOnce(
      success({
        data: [],
        pagination: { page: 1, pageSize: 100, total: 0 },
      }),
    );

    await listAllInferenceDeployments('proj-1');

    expect(mockGet).toHaveBeenCalledWith('/api/projects/{project}/inference', {
      params: {
        path: { project: 'proj-1' },
        query: { page: 1, pageSize: 100 },
      },
    });
  });

  it('forwards statusFilter and capability', async () => {
    mockGet.mockResolvedValueOnce(
      success({
        data: [],
        pagination: { page: 1, pageSize: 100, total: 0 },
      }),
    );

    await listAllInferenceDeployments('proj-1', {
      capability: 'chat',
      statusFilter: ['Running', 'Pending'],
    });

    expect(mockGet).toHaveBeenCalledWith('/api/projects/{project}/inference', {
      params: {
        path: { project: 'proj-1' },
        query: {
          page: 1,
          pageSize: 100,
          capability: 'chat',
          statusFilter: ['Running', 'Pending'],
        },
      },
    });
  });

  it('unwraps the paginated envelope to AIMService[] for a single page', async () => {
    mockGet.mockResolvedValueOnce(
      success({
        data: [{ id: 'svc-1' }, { id: 'svc-2' }],
        pagination: { page: 1, pageSize: 100, total: 2 },
      }),
    );

    const result = await listAllInferenceDeployments('proj-1');

    expect(result).toEqual([{ id: 'svc-1' }, { id: 'svc-2' }]);
  });

  it('walks subsequent pages and concatenates when total exceeds one page', async () => {
    mockGet
      .mockResolvedValueOnce(
        success({
          data: [{ id: 'svc-1' }],
          pagination: { page: 1, pageSize: 100, total: 250 },
        }),
      )
      .mockResolvedValueOnce(
        success({
          data: [{ id: 'svc-2' }],
          pagination: { page: 2, pageSize: 100, total: 250 },
        }),
      )
      .mockResolvedValueOnce(
        success({
          data: [{ id: 'svc-3' }],
          pagination: { page: 3, pageSize: 100, total: 250 },
        }),
      );

    const result = await listAllInferenceDeployments('proj-1');

    expect(result).toEqual([{ id: 'svc-1' }, { id: 'svc-2' }, { id: 'svc-3' }]);
    expect(mockGet).toHaveBeenCalledTimes(3);
    expect(mockGet).toHaveBeenNthCalledWith(
      2,
      '/api/projects/{project}/inference',
      {
        params: {
          path: { project: 'proj-1' },
          query: { page: 2, pageSize: 100 },
        },
      },
    );
    expect(mockGet).toHaveBeenNthCalledWith(
      3,
      '/api/projects/{project}/inference',
      {
        params: {
          path: { project: 'proj-1' },
          query: { page: 3, pageSize: 100 },
        },
      },
    );
  });

  it('returns [] and does not throw on typed client error (graceful degrade)', async () => {
    mockGet.mockResolvedValueOnce(failure(500));

    const result = await listAllInferenceDeployments('proj-1');

    expect(result).toEqual([]);
  });

  it('returns [] when a subsequent page fails (graceful degrade)', async () => {
    mockGet
      .mockResolvedValueOnce(
        success({
          data: [{ id: 'svc-1' }],
          pagination: { page: 1, pageSize: 100, total: 250 },
        }),
      )
      .mockResolvedValueOnce(failure(500));

    const result = await listAllInferenceDeployments('proj-1');

    expect(result).toEqual([]);
  });
});

describe('getInferenceDeployment', () => {
  it('GETs a single deployment with project and id path parameters', async () => {
    mockGet.mockResolvedValueOnce(success({ id: 'svc-1' }));

    await getInferenceDeployment('proj-1', 'svc-1');

    expect(mockGet).toHaveBeenCalledWith(
      '/api/projects/{project}/inference/{id}',
      { params: { path: { project: 'proj-1', id: 'svc-1' } } },
    );
  });

  it('throws APIRequestError when the typed client returns an error', async () => {
    mockGet.mockResolvedValueOnce(failure(404));

    await expect(getInferenceDeployment('proj-1', 'svc-1')).rejects.toThrow(
      /Failed to fetch inference deployment/,
    );
  });
});

describe('updateInferenceScaling', () => {
  it('PATCHes the typed deployment path with path params and full scaling body', async () => {
    mockPatch.mockResolvedValueOnce({ data: undefined, error: undefined });

    const payload = {
      minReplicas: 1,
      maxReplicas: 5,
      autoScaling: {
        metrics: [
          {
            type: 'PodMetric' as const,
            podmetric: {
              metric: {
                backend: 'opentelemetry' as const,
                metricNames: ['vllm:num_requests_running'],
                query: 'vllm:num_requests_running',
                operationOverTime: 'avg',
              },
              target: { type: 'Value', value: '10' },
            },
          },
        ],
      },
    };

    await updateInferenceScaling('proj-1', 'svc-1', payload);

    expect(mockPatch).toHaveBeenCalledWith(
      '/api/projects/{project}/inference/{id}',
      { params: { path: { project: 'proj-1', id: 'svc-1' } }, body: payload },
    );
  });

  it('throws APIRequestError when the typed client returns an error', async () => {
    mockPatch.mockResolvedValueOnce(failure(400));

    await expect(
      updateInferenceScaling('proj-1', 'svc-1', {
        minReplicas: 1,
        maxReplicas: 5,
        autoScaling: { metrics: [] },
      }),
    ).rejects.toThrow(/Failed to update inference scaling/);
  });
});

describe('updateInferenceAdapters', () => {
  it('PATCHes the complete desired adapter list, including an empty list', async () => {
    mockPatch.mockResolvedValueOnce(success(undefined));

    await updateInferenceAdapters('proj-1', 'svc-1', []);

    expect(mockPatch).toHaveBeenCalledWith(
      '/api/projects/{project}/inference/{id}',
      {
        params: { path: { project: 'proj-1', id: 'svc-1' } },
        body: { adapters: [] },
      },
    );
  });

  it('reports adapter update failures', async () => {
    mockPatch.mockResolvedValueOnce(failure(422));

    await expect(
      updateInferenceAdapters('proj-1', 'svc-1', ['invalid']),
    ).rejects.toThrow(/Failed to update inference adapters/);
  });
});

describe('attachAdapterToDeployment', () => {
  const deploymentWith = (adapterNames: string[]): AIMService =>
    ({
      id: 'svc-1',
      spec: {
        adapters: adapterNames.map((name) => ({ kind: 'AIMArtifact', name })),
      },
    }) as AIMService;

  beforeEach(() => {
    mockGet.mockResolvedValue(
      success(deploymentWith(['adapter-a', 'adapter-b'])),
    );
  });

  it('PATCHes the merged, deduped adapter set onto the deployment', async () => {
    mockPatch.mockResolvedValueOnce(success(undefined));

    await attachAdapterToDeployment(
      'proj-1',
      deploymentWith(['adapter-a', 'adapter-b']),
      'adapter-b',
    );

    expect(mockPatch).toHaveBeenCalledWith(
      '/api/projects/{project}/inference/{id}',
      {
        params: { path: { project: 'proj-1', id: 'svc-1' } },
        body: { adapters: ['adapter-a', 'adapter-b'] },
      },
    );
  });

  it('adds one adapter without dropping existing adapters', async () => {
    mockGet.mockResolvedValueOnce(success(deploymentWith(['existing'])));
    mockPatch.mockResolvedValueOnce(success(undefined));

    await attachAdapterToDeployment(
      'proj-1',
      deploymentWith(['existing']),
      'new',
    );

    expect(mockPatch).toHaveBeenCalledWith(
      '/api/projects/{project}/inference/{id}',
      {
        params: { path: { project: 'proj-1', id: 'svc-1' } },
        body: { adapters: ['existing', 'new'] },
      },
    );
  });

  it('rejects when the deployment has no ID', async () => {
    await expect(
      attachAdapterToDeployment('proj-1', {} as AIMService, 'adapter-a'),
    ).rejects.toThrow(/No inference deployment ID provided/);
  });

  it('throws APIRequestError when the typed client returns an error', async () => {
    mockPatch.mockResolvedValueOnce(failure(500));

    await expect(
      attachAdapterToDeployment('proj-1', deploymentWith([]), 'adapter-a'),
    ).rejects.toThrow(/Failed to update inference adapters/);
  });

  it('throws when an empty-body response is unsuccessful', async () => {
    mockPatch.mockResolvedValueOnce({
      data: undefined,
      error: undefined,
      response: { ok: false, status: 500, statusText: 'Error' },
    });

    await expect(
      attachAdapterToDeployment('proj-1', deploymentWith([]), 'adapter-a'),
    ).rejects.toThrow(/Failed to update inference adapters/);
  });
});

describe('deleteInferenceDeployment', () => {
  it('DELETEs the typed deployment path with path params', async () => {
    mockDelete.mockResolvedValueOnce({ data: undefined, error: undefined });

    await deleteInferenceDeployment('proj-1', 'svc-1');

    expect(mockDelete).toHaveBeenCalledWith(
      '/api/projects/{project}/inference/{id}',
      { params: { path: { project: 'proj-1', id: 'svc-1' } } },
    );
  });

  it('throws APIRequestError when the typed client returns an error', async () => {
    mockDelete.mockResolvedValueOnce(failure(500));

    await expect(deleteInferenceDeployment('proj-1', 'svc-1')).rejects.toThrow(
      /Failed to undeploy inference deployment/,
    );
  });

  it('rejects when project or id is missing', async () => {
    await expect(deleteInferenceDeployment('', 'svc-1')).rejects.toThrow(
      /No project provided/,
    );
    await expect(deleteInferenceDeployment('proj-1', '')).rejects.toThrow(
      /No deployment ID provided/,
    );
  });
});
