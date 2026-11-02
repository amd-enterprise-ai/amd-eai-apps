// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  listAllProjectFineTunedModels,
  listProjectFineTunedModels,
} from '@/lib/app/models';

// Typed-apiClient mock: the fine-tuning list rides the generated GET contract,
// so assert on the typed path/param shape rather than a URL string. Mock the
// client (not globalThis.fetch) — openapi-fetch builds a Request from the
// browser-relative baseUrl, which Node cannot parse in tests.
const mockGET = vi.fn();

vi.mock('@/lib/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api-client')>();
  return {
    ...actual,
    apiClient: {
      GET: (...args: unknown[]) => mockGET(...args),
    },
  };
});

const okData = (data: unknown) => ({
  data,
  error: undefined,
  response: { status: 200 } as Response,
});

const errData = (status: number) => ({
  data: undefined,
  error: { detail: 'boom' },
  response: { status, statusText: 'Server Error' } as Response,
});

beforeEach(() => {
  vi.clearAllMocks();
});

describe('listProjectFineTunedModels', () => {
  it('GETs the project fine-tuning list endpoint with default page=1/pageSize=10', async () => {
    mockGET.mockResolvedValueOnce(
      okData({ data: [], pagination: { page: 1, pageSize: 10, total: 0 } }),
    );

    await listProjectFineTunedModels('proj-1');

    expect(mockGET).toHaveBeenCalledWith(
      '/api/projects/{project}/fine-tuning/models',
      {
        params: {
          path: { project: 'proj-1' },
          query: { page: 1, pageSize: 10 },
        },
      },
    );
  });

  it('forwards explicit page and pageSize to the query string', async () => {
    mockGET.mockResolvedValueOnce(
      okData({ data: [], pagination: { page: 3, pageSize: 25, total: 80 } }),
    );

    await listProjectFineTunedModels('proj-1', { page: 3, pageSize: 25 });

    expect(mockGET).toHaveBeenCalledWith(
      '/api/projects/{project}/fine-tuning/models',
      {
        params: {
          path: { project: 'proj-1' },
          query: { page: 3, pageSize: 25 },
        },
      },
    );
  });

  it('returns the paginated envelope verbatim', async () => {
    const envelope = {
      data: [{ metadata: { name: 'ft-1' } }, { metadata: { name: 'ft-2' } }],
      pagination: { page: 1, pageSize: 10, total: 2 },
    };
    mockGET.mockResolvedValueOnce(okData(envelope));

    const result = await listProjectFineTunedModels('proj-1');

    expect(result).toEqual(envelope);
  });

  it('throws APIRequestError on non-OK response', async () => {
    mockGET.mockResolvedValueOnce(errData(500));

    await expect(listProjectFineTunedModels('proj-1')).rejects.toThrow(
      /Failed to get fine-tuned models/,
    );
  });
});

describe('listAllProjectFineTunedModels', () => {
  it('GETs the project fine-tuning list endpoint with pageSize=100 on the first page', async () => {
    mockGET.mockResolvedValueOnce(
      okData({ data: [], pagination: { page: 1, pageSize: 100, total: 0 } }),
    );

    await listAllProjectFineTunedModels('proj-1');

    expect(mockGET).toHaveBeenCalledWith(
      '/api/projects/{project}/fine-tuning/models',
      {
        params: {
          path: { project: 'proj-1' },
          query: { page: 1, pageSize: 100 },
        },
      },
    );
  });

  it('unwraps the paginated envelope to AIMModel[] for a single page', async () => {
    mockGET.mockResolvedValueOnce(
      okData({
        data: [{ metadata: { name: 'ft-1' } }, { metadata: { name: 'ft-2' } }],
        pagination: { page: 1, pageSize: 100, total: 2 },
      }),
    );

    const result = await listAllProjectFineTunedModels('proj-1');

    expect(result).toEqual([
      { metadata: { name: 'ft-1' } },
      { metadata: { name: 'ft-2' } },
    ]);
    expect(mockGET).toHaveBeenCalledTimes(1);
  });

  it('walks subsequent pages and concatenates when total exceeds one page', async () => {
    mockGET
      .mockResolvedValueOnce(
        okData({
          data: [{ metadata: { name: 'ft-1' } }],
          pagination: { page: 1, pageSize: 100, total: 250 },
        }),
      )
      .mockResolvedValueOnce(
        okData({
          data: [{ metadata: { name: 'ft-2' } }],
          pagination: { page: 2, pageSize: 100, total: 250 },
        }),
      )
      .mockResolvedValueOnce(
        okData({
          data: [{ metadata: { name: 'ft-3' } }],
          pagination: { page: 3, pageSize: 100, total: 250 },
        }),
      );

    const result = await listAllProjectFineTunedModels('proj-1');

    expect(result).toEqual([
      { metadata: { name: 'ft-1' } },
      { metadata: { name: 'ft-2' } },
      { metadata: { name: 'ft-3' } },
    ]);
    expect(mockGET).toHaveBeenCalledTimes(3);
    expect(mockGET.mock.calls[1][1].params.query.page).toBe(2);
    expect(mockGET.mock.calls[2][1].params.query.page).toBe(3);
  });

  it('returns [] and does not throw on non-OK response (graceful degrade)', async () => {
    mockGET.mockResolvedValueOnce(errData(500));

    const result = await listAllProjectFineTunedModels('proj-1');

    expect(result).toEqual([]);
  });

  it('returns [] when a subsequent page fails (graceful degrade)', async () => {
    // total=150, pageSize=100 -> totalPages=2, so only one remaining page is fetched.
    mockGET
      .mockResolvedValueOnce(
        okData({
          data: [{ metadata: { name: 'ft-1' } }],
          pagination: { page: 1, pageSize: 100, total: 150 },
        }),
      )
      .mockResolvedValueOnce(errData(500));

    const result = await listAllProjectFineTunedModels('proj-1');

    expect(result).toEqual([]);
  });
});
