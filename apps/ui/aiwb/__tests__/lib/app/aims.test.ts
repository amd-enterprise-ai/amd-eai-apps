// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { afterEach, describe, expect, it, Mock, vi } from 'vitest';

import {
  getAimClusterProfileByName,
  getProjectAimProfileByName,
  getProjectFineTunedModel,
  listAimClusterProfilesPage,
  listProjectAimProfilesPage,
  resolveBaseModelSource,
} from '@/lib/app/aims';
import { apiClient } from '@/lib/api-client';
import type { AIMClusterModel, AIMModel } from '@/types/aims';

vi.mock('@/lib/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api-client')>();
  return {
    ...actual,
    apiClient: { GET: vi.fn(), POST: vi.fn(), PATCH: vi.fn(), DELETE: vi.fn() },
  };
});

const mockGet = apiClient.GET as Mock;

afterEach(() => {
  mockGet.mockReset();
});

const okData = (data: unknown) => ({
  data,
  error: undefined,
  response: { status: 200 } as Response,
});

const errData = (status: number) => ({
  data: undefined,
  error: { detail: 'boom' },
  response: { status, statusText: 'Not Found' } as Response,
});

describe('getProjectFineTunedModel', () => {
  it('GETs the fine-tuning model endpoint with path params mapping model_id to resourceName', async () => {
    mockGet.mockResolvedValueOnce(okData({ metadata: { name: 'ft-model-1' } }));

    const result = await getProjectFineTunedModel('ft-model-1', 'proj-1');

    expect(mockGet).toHaveBeenCalledWith(
      '/api/projects/{project}/fine-tuning/models/{model_id}',
      { params: { path: { project: 'proj-1', model_id: 'ft-model-1' } } },
    );
    expect(result).toEqual({ metadata: { name: 'ft-model-1' } });
  });

  it('throws APIRequestError with message prefix on error response', async () => {
    mockGet.mockResolvedValueOnce(errData(404));

    await expect(
      getProjectFineTunedModel('ft-model-1', 'proj-1'),
    ).rejects.toThrow(/Failed to fetch AIM model/);
  });

  it('rejects when resourceName is empty', async () => {
    await expect(getProjectFineTunedModel('', 'proj-1')).rejects.toThrow(
      /No AIM model resource name provided/,
    );
  });
});

describe('listAimClusterProfilesPage', () => {
  it('GETs the cluster profiles endpoint with page and pageSize params', async () => {
    mockGet.mockResolvedValueOnce(
      okData({ data: [], pagination: { page: 1, pageSize: 10, total: 0 } }),
    );

    const result = await listAimClusterProfilesPage(1, 10);

    expect(mockGet).toHaveBeenCalledWith('/api/inference/profiles', {
      params: { query: { page: 1, pageSize: 10, aimId: undefined } },
    });
    expect(result).toEqual({
      data: [],
      pagination: { page: 1, pageSize: 10, total: 0 },
    });
  });

  it('forwards aimId array in params.query', async () => {
    mockGet.mockResolvedValueOnce(
      okData({ data: [], pagination: { page: 1, pageSize: 10, total: 0 } }),
    );

    await listAimClusterProfilesPage(1, 10, { aimIds: ['aim-1', 'aim-2'] });

    expect(mockGet).toHaveBeenCalledWith('/api/inference/profiles', {
      params: { query: { page: 1, pageSize: 10, aimId: ['aim-1', 'aim-2'] } },
    });
  });

  it('filters out falsy aimIds before forwarding', async () => {
    mockGet.mockResolvedValueOnce(
      okData({ data: [], pagination: { page: 1, pageSize: 10, total: 0 } }),
    );

    await listAimClusterProfilesPage(1, 10, { aimIds: ['aim-1', '', 'aim-2'] });

    const call = mockGet.mock.calls[0][1];
    expect(call.params.query.aimId).toEqual(['aim-1', 'aim-2']);
  });

  it('throws APIRequestError with message prefix on error response', async () => {
    mockGet.mockResolvedValueOnce(errData(500));

    await expect(listAimClusterProfilesPage(1, 10)).rejects.toThrow(
      /Failed to fetch AIM cluster profiles/,
    );
  });
});

describe('getAimClusterProfileByName', () => {
  it('GETs the cluster profile by name with path param', async () => {
    mockGet.mockResolvedValueOnce(okData({ metadata: { name: 'profile-1' } }));

    const result = await getAimClusterProfileByName('profile-1');

    expect(mockGet).toHaveBeenCalledWith('/api/inference/profiles/{name}', {
      params: { path: { name: 'profile-1' } },
    });
    expect(result).toEqual({ metadata: { name: 'profile-1' } });
  });

  it('throws APIRequestError including the profile name on error response', async () => {
    mockGet.mockResolvedValueOnce(errData(404));

    await expect(getAimClusterProfileByName('profile-1')).rejects.toThrow(
      /Failed to fetch AIM cluster profile 'profile-1'/,
    );
  });

  it('rejects when name is empty', async () => {
    await expect(getAimClusterProfileByName('')).rejects.toThrow(
      /No profile name provided/,
    );
  });
});

describe('listProjectAimProfilesPage', () => {
  it('GETs the project profiles endpoint with path and query params', async () => {
    mockGet.mockResolvedValueOnce(
      okData({ data: [], pagination: { page: 1, pageSize: 10, total: 0 } }),
    );

    const result = await listProjectAimProfilesPage('proj-1', 1, 10);

    expect(mockGet).toHaveBeenCalledWith('/api/projects/{project}/profiles', {
      params: {
        path: { project: 'proj-1' },
        query: { page: 1, pageSize: 10, aimId: undefined },
      },
    });
    expect(result).toEqual({
      data: [],
      pagination: { page: 1, pageSize: 10, total: 0 },
    });
  });

  it('forwards aimId array in params.query', async () => {
    mockGet.mockResolvedValueOnce(
      okData({ data: [], pagination: { page: 1, pageSize: 10, total: 0 } }),
    );

    await listProjectAimProfilesPage('proj-1', 1, 10, {
      aimIds: ['aim-1', 'aim-2'],
    });

    expect(mockGet).toHaveBeenCalledWith('/api/projects/{project}/profiles', {
      params: {
        path: { project: 'proj-1' },
        query: { page: 1, pageSize: 10, aimId: ['aim-1', 'aim-2'] },
      },
    });
  });

  it('filters out falsy aimIds before forwarding', async () => {
    mockGet.mockResolvedValueOnce(
      okData({ data: [], pagination: { page: 1, pageSize: 10, total: 0 } }),
    );

    await listProjectAimProfilesPage('proj-1', 1, 10, {
      aimIds: ['aim-1', '', 'aim-2'],
    });

    const call = mockGet.mock.calls[0][1];
    expect(call.params.query.aimId).toEqual(['aim-1', 'aim-2']);
  });

  it('throws APIRequestError with message prefix on error response', async () => {
    mockGet.mockResolvedValueOnce(errData(500));

    await expect(listProjectAimProfilesPage('proj-1', 1, 10)).rejects.toThrow(
      /Failed to fetch project AIM profiles/,
    );
  });

  it('rejects when project is empty', async () => {
    await expect(listProjectAimProfilesPage('', 1, 10)).rejects.toThrow(
      /No project selected/,
    );
  });
});

describe('getProjectAimProfileByName', () => {
  it('GETs the project profile by name with path params', async () => {
    mockGet.mockResolvedValueOnce(okData({ metadata: { name: 'profile-1' } }));

    const result = await getProjectAimProfileByName('proj-1', 'profile-1');

    expect(mockGet).toHaveBeenCalledWith(
      '/api/projects/{project}/profiles/{name}',
      { params: { path: { project: 'proj-1', name: 'profile-1' } } },
    );
    expect(result).toEqual({ metadata: { name: 'profile-1' } });
  });

  it('throws APIRequestError including the profile name on error response', async () => {
    mockGet.mockResolvedValueOnce(errData(404));

    await expect(
      getProjectAimProfileByName('proj-1', 'profile-1'),
    ).rejects.toThrow(/Failed to fetch project AIM profile 'profile-1'/);
  });

  it('rejects when project is empty', async () => {
    await expect(getProjectAimProfileByName('', 'profile-1')).rejects.toThrow(
      /No project selected/,
    );
  });

  it('rejects when name is empty', async () => {
    await expect(getProjectAimProfileByName('proj-1', '')).rejects.toThrow(
      /No profile name provided/,
    );
  });
});

const baseModel = (spec: Partial<AIMModel['spec']>): AIMModel => ({
  metadata: { name: 'ft-1', creationTimestamp: '2026-01-01T00:00:00Z' },
  spec: { image: '', ...spec },
  status: { status: 'Ready' },
});

describe('resolveBaseModelSource', () => {
  it('reads the legacy flat spec.modelSources when present', () => {
    const model = baseModel({
      modelSources: [{ modelId: 'org/base', sourceUri: 's3://bucket/base' }],
    });
    expect(resolveBaseModelSource(model)).toEqual({
      modelId: 'org/base',
      sourceUri: 's3://bucket/base',
    });
  });

  it('falls back to the v1alpha2 profile override modelSources', () => {
    const model = baseModel({
      profiles: {
        overrides: {
          modelSources: [
            { modelId: 'org/override', sourceUri: 's3://bucket/override' },
          ],
        },
      },
    });
    expect(resolveBaseModelSource(model)).toEqual({
      modelId: 'org/override',
      sourceUri: 's3://bucket/override',
    });
  });

  it('prefers the flat field over the profile override when both exist', () => {
    const model = baseModel({
      modelSources: [{ modelId: 'org/flat', sourceUri: 's3://bucket/flat' }],
      profiles: {
        overrides: {
          modelSources: [
            { modelId: 'org/override', sourceUri: 's3://bucket/override' },
          ],
        },
      },
    });
    expect(resolveBaseModelSource(model)?.modelId).toBe('org/flat');
  });

  it('returns null when neither source field is populated', () => {
    expect(resolveBaseModelSource(baseModel({}))).toBeNull();
  });

  it('returns null for cluster models, which carry no weights source', () => {
    const clusterModel = {
      metadata: { name: 'cluster-aim' },
      spec: { image: 'amdenterpriseai/aim-base:0.10' },
      status: { status: 'Ready' },
    } as unknown as AIMClusterModel;
    expect(resolveBaseModelSource(clusterModel)).toBeNull();
  });
});
