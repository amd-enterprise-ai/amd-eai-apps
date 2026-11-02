// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  deleteAdapterArtifact,
  getAdapterArtifact,
  getAdapterArtifacts,
  listAllAdapterArtifacts,
  listAdapterArtifacts,
  waitForAdapterArtifactRemoval,
} from '@/lib/app/artifacts';

const mockGET = vi.fn();
const mockDELETE = vi.fn();

vi.mock('@/lib/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api-client')>();
  return {
    ...actual,
    apiClient: {
      GET: (...args: unknown[]) => mockGET(...args),
      DELETE: (...args: unknown[]) => mockDELETE(...args),
    },
  };
});

const artifact = {
  storage: {
    uri: 's3://example-bucket/project/adapters/adapter-1/',
    registration: 'Registered',
    readiness: 'NotReady',
  },
  artifact: {
    metadata: {
      name: 'adapter-1',
      namespace: 'project',
      uid: 'adapter-uid',
      annotations: {
        'airm.silogen.ai/submitter': 'user@example.com',
        'aiwb.apps.eai.amd.com/description': 'Customer support adapter',
        'aiwb.apps.eai.amd.com/display-name': 'Support LoRA',
      },
      creationTimestamp: '2026-08-11T12:31:31Z',
    },
    spec: {
      type: 'adapter',
      modelId: 'example-org/support-lora',
      compatibleWith: ['example-org/base-model'],
      rank: 16,
    },
    status: {
      status: 'Ready',
    },
  },
};

const okData = (data: unknown) => ({
  data,
  error: undefined,
  response: { status: 200 } as Response,
});

beforeEach(() => {
  vi.clearAllMocks();
});

describe('listAdapterArtifacts', () => {
  it('requests registered adapters with server-side pagination', async () => {
    mockGET.mockResolvedValue(
      okData({
        data: [],
        pagination: { page: 3, pageSize: 25, total: 0 },
      }),
    );

    await listAdapterArtifacts('project', { page: 3, pageSize: 25 });

    expect(mockGET).toHaveBeenCalledWith('/api/projects/{project}/artifacts', {
      params: {
        path: { project: 'project' },
        query: { page: 3, pageSize: 25, type: ['adapter'] },
      },
    });
  });

  it('maps registered artifacts without collapsing controller and storage status', async () => {
    mockGET.mockResolvedValue(
      okData({
        data: [artifact],
        pagination: { page: 1, pageSize: 10, total: 1 },
      }),
    );

    const result = await listAdapterArtifacts('project');

    expect(result.data).toEqual([
      {
        id: 'adapter-uid',
        name: 'adapter-1',
        displayName: 'Support LoRA',
        description: 'Customer support adapter',
        modelId: 'example-org/support-lora',
        compatibleWith: ['example-org/base-model'],
        rank: 16,
        status: 'Ready',
        readiness: 'NotReady',
        uri: 's3://example-bucket/project/adapters/adapter-1/',
        createdAt: '2026-08-11T12:31:31Z',
        createdBy: 'user@example.com',
      },
    ]);
  });

  it('asks the API which adapters a given deployment can serve', async () => {
    mockGET.mockResolvedValue(
      okData({ data: [], pagination: { page: 1, pageSize: 10, total: 0 } }),
    );

    await listAdapterArtifacts('project', {
      servableBy: '11111111-2222-3333-4444-555555555555',
    });

    expect(mockGET.mock.calls[0][1].params.query.servableBy).toBe(
      '11111111-2222-3333-4444-555555555555',
    );
  });

  it('leaves the deployment out of the query when no servability question is asked', async () => {
    mockGET.mockResolvedValue(
      okData({ data: [], pagination: { page: 1, pageSize: 10, total: 0 } }),
    );

    await listAdapterArtifacts('project');

    expect(mockGET.mock.calls[0][1].params.query.servableBy).toBeUndefined();
  });

  it('carries the API servability verdict through to the adapter', async () => {
    mockGET.mockResolvedValue(
      okData({
        data: [
          { ...artifact, servable: true },
          {
            ...artifact,
            servable: false,
            artifact: {
              ...artifact.artifact,
              metadata: { ...artifact.artifact.metadata, name: 'adapter-2' },
            },
          },
        ],
        pagination: { page: 1, pageSize: 10, total: 2 },
      }),
    );

    const result = await listAdapterArtifacts('project');

    expect(result.data.map(({ servable }) => servable)).toEqual([true, false]);
  });

  it('keeps an unanswered servability question distinct from a negative answer', async () => {
    mockGET.mockResolvedValue(
      okData({
        data: [{ ...artifact, servable: null }],
        pagination: { page: 1, pageSize: 10, total: 1 },
      }),
    );

    const result = await listAdapterArtifacts('project');

    // Null is the API saying it was not asked; reading it as false would let a
    // picker hide an adapter it has no verdict on.
    expect(result.data[0]!.servable).toBeNull();
  });

  it('throws when the adapter list request fails', async () => {
    mockGET.mockResolvedValue({
      data: undefined,
      error: { detail: 'boom' },
      response: { status: 500, statusText: 'Server Error' } as Response,
    });

    await expect(listAdapterArtifacts('project')).rejects.toThrow(
      'Failed to list adapters: boom',
    );
  });
});

describe('listAllAdapterArtifacts', () => {
  it('walks every page and returns all registered adapters', async () => {
    mockGET
      .mockResolvedValueOnce(
        okData({
          data: [artifact],
          pagination: { page: 1, pageSize: 100, total: 101 },
        }),
      )
      .mockResolvedValueOnce(
        okData({
          data: [
            {
              ...artifact,
              artifact: {
                ...artifact.artifact,
                metadata: {
                  ...artifact.artifact.metadata,
                  name: 'adapter-2',
                  uid: 'adapter-uid-2',
                },
              },
            },
          ],
          pagination: { page: 2, pageSize: 100, total: 101 },
        }),
      );

    const result = await listAllAdapterArtifacts('project');

    expect(result.map(({ name }) => name)).toEqual(['adapter-1', 'adapter-2']);
    expect(mockGET).toHaveBeenCalledTimes(2);
    expect(mockGET.mock.calls[0][1].params.query.page).toBe(1);
    expect(mockGET.mock.calls[1][1].params.query.page).toBe(2);
  });

  it('asks the same servability question on every page it walks', async () => {
    mockGET
      .mockResolvedValueOnce(
        okData({
          data: [artifact],
          pagination: { page: 1, pageSize: 100, total: 101 },
        }),
      )
      .mockResolvedValueOnce(
        okData({
          data: [artifact],
          pagination: { page: 2, pageSize: 100, total: 101 },
        }),
      );

    await listAllAdapterArtifacts('project', 'deployment-id');

    expect(
      mockGET.mock.calls.map((call) => call[1].params.query.servableBy),
    ).toEqual(['deployment-id', 'deployment-id']);
  });
});

describe('getAdapterArtifact', () => {
  it('gets a registered adapter by resource name', async () => {
    mockGET.mockResolvedValue(okData(artifact));

    await expect(getAdapterArtifact('project', 'adapter-1')).resolves.toEqual(
      artifact,
    );
    expect(mockGET).toHaveBeenCalledWith(
      '/api/projects/{project}/artifacts/{name}',
      {
        params: {
          path: { project: 'project', name: 'adapter-1' },
        },
      },
    );
  });

  it('throws when the adapter details request fails', async () => {
    mockGET.mockResolvedValue({
      data: undefined,
      error: { detail: 'Adapter not found' },
      response: { status: 404, statusText: 'Not Found' } as Response,
    });

    await expect(getAdapterArtifact('project', 'missing')).rejects.toThrow(
      'Failed to get adapter: Adapter not found',
    );
  });
});

describe('getAdapterArtifacts', () => {
  it('drops adapters removed from the project without listing every adapter', async () => {
    mockGET.mockResolvedValueOnce(okData(artifact)).mockResolvedValueOnce({
      data: undefined,
      error: { detail: 'Adapter not found' },
      response: { status: 404, statusText: 'Not Found' } as Response,
    });

    await expect(
      getAdapterArtifacts('project', ['adapter-1', 'missing']),
    ).resolves.toEqual([
      expect.objectContaining({
        name: 'adapter-1',
        displayName: 'Support LoRA',
        rank: 16,
      }),
    ]);
    expect(mockGET).toHaveBeenCalledTimes(2);
    expect(mockGET).toHaveBeenNthCalledWith(
      1,
      '/api/projects/{project}/artifacts/{name}',
      { params: { path: { project: 'project', name: 'adapter-1' } } },
    );
  });

  it('bounds in-flight lookups rather than bursting one request per adapter', async () => {
    let inFlight = 0;
    let peakInFlight = 0;
    mockGET.mockImplementation(async () => {
      inFlight += 1;
      peakInFlight = Math.max(peakInFlight, inFlight);
      await new Promise((resolve) => setTimeout(resolve, 0));
      inFlight -= 1;
      return okData(artifact);
    });
    const names = Array.from({ length: 12 }, (_, index) => `adapter-${index}`);

    await expect(getAdapterArtifacts('project', names)).resolves.toHaveLength(
      12,
    );

    expect(mockGET).toHaveBeenCalledTimes(12);
    expect(peakInFlight).toBeLessThanOrEqual(4);
  });

  it('surfaces a transient fetch failure instead of hiding a still-attached adapter', async () => {
    mockGET.mockResolvedValueOnce(okData(artifact)).mockResolvedValueOnce({
      data: undefined,
      error: { detail: 'Service unavailable' },
      response: { status: 503, statusText: 'Service Unavailable' } as Response,
    });

    await expect(
      getAdapterArtifacts('project', ['adapter-1', 'adapter-2']),
    ).rejects.toThrow('Service unavailable');
  });
});

describe('deleteAdapterArtifact', () => {
  it('deletes a registered adapter by resource name', async () => {
    mockDELETE.mockResolvedValue({
      error: undefined,
      response: { ok: true, status: 202 } as Response,
    });

    await deleteAdapterArtifact('project', 'adapter-1');

    expect(mockDELETE).toHaveBeenCalledWith(
      '/api/projects/{project}/artifacts/{name}',
      {
        params: {
          path: { project: 'project', name: 'adapter-1' },
          query: {},
        },
      },
    );
  });

  it('surfaces the blocking deployment detail from a conflict', async () => {
    mockDELETE.mockResolvedValue({
      error: {
        detail:
          "Artifact 'adapter-1' is referenced by AIMService(s): deployment-1.",
      },
      response: { ok: false, status: 409 } as Response,
    });

    await expect(deleteAdapterArtifact('project', 'adapter-1')).rejects.toThrow(
      'deployment-1',
    );
  });
});

describe('waitForAdapterArtifactRemoval', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('resolves once the deleted artifact starts returning not found', async () => {
    mockGET.mockResolvedValueOnce(okData(artifact)).mockResolvedValueOnce({
      data: undefined,
      error: { detail: 'Adapter not found' },
      response: { status: 404, statusText: 'Not Found' } as Response,
    });

    const removal = waitForAdapterArtifactRemoval('project', 'adapter-1');
    const assertion = expect(removal).resolves.toBeUndefined();
    await vi.runAllTimersAsync();
    await assertion;

    expect(mockGET).toHaveBeenCalledTimes(2);
  });

  it('gives up without throwing once polling attempts are exhausted', async () => {
    mockGET.mockResolvedValue(okData(artifact));

    const removal = waitForAdapterArtifactRemoval('project', 'adapter-1');
    const assertion = expect(removal).resolves.toBeUndefined();
    await vi.runAllTimersAsync();
    await assertion;
  });

  it('propagates a failure unrelated to the artifact having been removed', async () => {
    mockGET.mockResolvedValue({
      data: undefined,
      error: { detail: 'Service unavailable' },
      response: { status: 503, statusText: 'Service Unavailable' } as Response,
    });

    const removal = waitForAdapterArtifactRemoval('project', 'adapter-1');
    const assertion = expect(removal).rejects.toThrow('Service unavailable');
    await vi.runAllTimersAsync();
    await assertion;
  });
});
