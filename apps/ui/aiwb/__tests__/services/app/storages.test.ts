// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { createProjectStorage, fetchProjectStorages } from '@/lib/app/storages';

import { APIRequestError } from '@amdenterpriseai/utils/app';

import type { components } from '@/types/api';

// Mock the typed apiClient directly (not globalThis.fetch) so assertions ride
// the typed path/param contract — see secrets.test.ts for the canonical
// pattern.
const mockGET = vi.fn();
const mockPOST = vi.fn();

vi.mock('@/lib/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api-client')>();
  return {
    ...actual,
    apiClient: {
      GET: (...args: unknown[]) => mockGET(...args),
      POST: (...args: unknown[]) => mockPOST(...args),
    },
  };
});

type ProjectStorageResponse = components['schemas']['ProjectStorageResponse'];

const makeStorage = (i: number): ProjectStorageResponse => ({
  name: `storage-${i}`,
  displayName: `Storage ${i}`,
  project: 'proj1',
  type: 'S3',
  secretName: `s3-secret-${i}`,
  spec: { bucketUrl: 'https://s3.example.com/bucket', region: 'us-east-1' },
});

const okList = (data: ProjectStorageResponse[]) => ({
  data: { data },
  error: undefined,
  response: { status: 200 } as Response,
});

beforeEach(() => {
  vi.clearAllMocks();
});

describe('storages service', () => {
  describe('fetchProjectStorages', () => {
    it('fetches storages via the typed client', async () => {
      mockGET.mockResolvedValue(okList([makeStorage(1)]));

      const result = await fetchProjectStorages('proj1');

      expect(mockGET).toHaveBeenCalledTimes(1);
      expect(mockGET).toHaveBeenCalledWith('/api/projects/{project}/storages', {
        params: {
          path: { project: 'proj1' },
          query: { type: undefined },
        },
      });
      expect(result.data).toHaveLength(1);
    });

    it('forwards the type filter as a typed query param', async () => {
      mockGET.mockResolvedValue(okList([]));

      await fetchProjectStorages('proj1', 'S3');

      expect(mockGET).toHaveBeenCalledWith('/api/projects/{project}/storages', {
        params: {
          path: { project: 'proj1' },
          query: { type: 'S3' },
        },
      });
    });

    it('handles an empty storages list', async () => {
      mockGET.mockResolvedValue(okList([]));

      const result = await fetchProjectStorages('proj1');

      expect(result).toEqual({ data: [] });
    });

    it('throws APIRequestError when the client reports an error', async () => {
      mockGET.mockResolvedValue({
        data: undefined,
        error: { detail: 'boom' },
        response: { status: 502 } as Response,
      });

      await expect(fetchProjectStorages('proj1')).rejects.toThrow(
        APIRequestError,
      );
    });

    it('throws APIRequestError when projectId is empty (no request)', async () => {
      await expect(fetchProjectStorages('')).rejects.toThrow(APIRequestError);
      expect(mockGET).not.toHaveBeenCalled();
    });
  });

  describe('createProjectStorage', () => {
    it('POSTs the request body and returns the created storage', async () => {
      const created = makeStorage(1);
      mockPOST.mockResolvedValue({
        data: created,
        error: undefined,
        response: { status: 201 } as Response,
      });
      const request = {
        displayName: 'Storage 1',
        type: 'S3' as const,
        secretName: 's3-secret-1',
        spec: {
          bucketUrl: 'https://s3.example.com/bucket',
          region: 'us-east-1',
        },
      };

      const result = await createProjectStorage('proj1', request);

      expect(mockPOST).toHaveBeenCalledWith(
        '/api/projects/{project}/storages',
        { params: { path: { project: 'proj1' } }, body: request },
      );
      expect(result).toBe(created);
    });

    it('throws APIRequestError on failure', async () => {
      mockPOST.mockResolvedValue({
        data: undefined,
        error: { detail: 'conflict' },
        response: { status: 409 } as Response,
      });

      await expect(
        createProjectStorage('proj1', {
          displayName: 'x',
          type: 'S3',
          secretName: 's3-secret',
          spec: {},
        }),
      ).rejects.toThrow(APIRequestError);
    });

    it('throws APIRequestError when projectId is empty (no request)', async () => {
      await expect(
        createProjectStorage('', {
          displayName: 'x',
          type: 'S3',
          secretName: 's3-secret',
          spec: {},
        }),
      ).rejects.toThrow(APIRequestError);
      expect(mockPOST).not.toHaveBeenCalled();
    });
  });
});
