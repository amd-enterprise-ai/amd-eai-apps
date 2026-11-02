// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  createProjectSecret,
  deleteProjectSecret,
  fetchProjectSecrets,
} from '@/lib/app/secrets';

import { APIRequestError } from '@amdenterpriseai/utils/app';

import type { components } from '@/types/api';

// Mock the typed apiClient directly (not globalThis.fetch) so assertions ride
// the typed path/param contract — see datasets.test.ts for the canonical
// pattern.
const mockGET = vi.fn();
const mockPOST = vi.fn();
const mockDELETE = vi.fn();

vi.mock('@/lib/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api-client')>();
  return {
    ...actual,
    apiClient: {
      GET: (...args: unknown[]) => mockGET(...args),
      POST: (...args: unknown[]) => mockPOST(...args),
      DELETE: (...args: unknown[]) => mockDELETE(...args),
    },
  };
});

vi.mock('@amdenterpriseai/utils/app', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@amdenterpriseai/utils/app')>();
  return {
    ...actual,
    getErrorMessage: vi.fn().mockResolvedValue('error message'),
  };
});

type SecretResponse = components['schemas']['SecretResponse'];

const makeSecret = (i: number): SecretResponse => ({
  displayName: `secret-${i}`,
  useCase: 'Generic',
  metadata: {
    name: `wb-secret-${i}`,
    namespace: 'proj1',
    creationTimestamp: '2024-01-01T00:00:00Z',
  },
});

const okPage = (data: SecretResponse[], total: number) => ({
  data: { data, pagination: { page: 1, pageSize: 100, total } },
  error: undefined,
  response: { status: 200 } as Response,
});

beforeEach(() => {
  vi.clearAllMocks();
});

describe('secrets service', () => {
  describe('fetchProjectSecrets', () => {
    it('fetches a single page via the typed client', async () => {
      mockGET.mockResolvedValue(okPage([makeSecret(1)], 1));

      const result = await fetchProjectSecrets('proj1');

      expect(mockGET).toHaveBeenCalledTimes(1);
      expect(mockGET).toHaveBeenCalledWith('/api/projects/{project}/secrets', {
        params: {
          path: { project: 'proj1' },
          query: { page: 1, pageSize: 100, useCase: undefined },
        },
      });
      expect(result.data).toHaveLength(1);
    });

    it('walks every page when total exceeds one page', async () => {
      const pageOne = Array.from({ length: 100 }, (_, i) => makeSecret(i));
      const pageTwo = Array.from({ length: 100 }, (_, i) =>
        makeSecret(100 + i),
      );
      const pageThree = Array.from({ length: 50 }, (_, i) =>
        makeSecret(200 + i),
      );
      mockGET.mockImplementation(
        (_path: string, opts: { params: { query: { page: number } } }) => {
          const page = opts.params.query.page;
          const data = page === 1 ? pageOne : page === 2 ? pageTwo : pageThree;
          return Promise.resolve({
            data: { data, pagination: { page, pageSize: 100, total: 250 } },
            error: undefined,
            response: { status: 200 } as Response,
          });
        },
      );

      const result = await fetchProjectSecrets('proj1');

      expect(mockGET).toHaveBeenCalledTimes(3);
      expect(result.data).toHaveLength(250);
    });

    it('handles an empty secrets list', async () => {
      mockGET.mockResolvedValue(okPage([], 0));

      const result = await fetchProjectSecrets('proj1');

      expect(mockGET).toHaveBeenCalledTimes(1);
      expect(result).toEqual({ data: [] });
    });

    it('forwards the useCase filter as a typed query param', async () => {
      mockGET.mockResolvedValue(okPage([], 0));

      await fetchProjectSecrets('proj1', 'ImagePullSecret');

      expect(mockGET).toHaveBeenCalledWith('/api/projects/{project}/secrets', {
        params: {
          path: { project: 'proj1' },
          query: { page: 1, pageSize: 100, useCase: 'ImagePullSecret' },
        },
      });
    });

    it('throws APIRequestError when the client reports an error', async () => {
      mockGET.mockResolvedValue({
        data: undefined,
        error: { detail: 'boom' },
        response: { status: 500 } as Response,
      });

      await expect(fetchProjectSecrets('proj1')).rejects.toThrow(
        APIRequestError,
      );
    });

    it('throws APIRequestError when projectId is empty (no request)', async () => {
      await expect(fetchProjectSecrets('')).rejects.toThrow(APIRequestError);
      expect(mockGET).not.toHaveBeenCalled();
    });
  });

  describe('deleteProjectSecret', () => {
    it('calls DELETE with the typed path and succeeds', async () => {
      mockDELETE.mockResolvedValue({
        error: undefined,
        response: { status: 204 } as Response,
      });

      await expect(
        deleteProjectSecret('proj1', 'sec1'),
      ).resolves.toBeUndefined();

      expect(mockDELETE).toHaveBeenCalledWith(
        '/api/projects/{project}/secrets/{secret_name}',
        { params: { path: { project: 'proj1', secret_name: 'sec1' } } },
      );
    });

    it('throws APIRequestError on failure', async () => {
      mockDELETE.mockResolvedValue({
        error: { detail: 'boom' },
        response: { status: 400 } as Response,
      });

      await expect(deleteProjectSecret('proj1', 'sec1')).rejects.toThrow(
        APIRequestError,
      );
    });
  });

  describe('createProjectSecret', () => {
    it('POSTs the request body and returns the created secret', async () => {
      const created = makeSecret(1);
      mockPOST.mockResolvedValue({
        data: created,
        error: undefined,
        response: { status: 201 } as Response,
      });
      const request = {
        displayName: 'secret-1',
        data: { token: 'dmFsdWU=' },
        useCase: 'Generic' as const,
      };

      const result = await createProjectSecret('proj1', request);

      expect(mockPOST).toHaveBeenCalledWith('/api/projects/{project}/secrets', {
        params: { path: { project: 'proj1' } },
        body: request,
      });
      expect(result).toBe(created);
    });

    it('throws APIRequestError on failure', async () => {
      mockPOST.mockResolvedValue({
        data: undefined,
        error: { detail: 'conflict' },
        response: { status: 409 } as Response,
      });

      await expect(
        createProjectSecret('proj1', {
          displayName: 'x',
          data: {},
          useCase: 'Generic',
        }),
      ).rejects.toThrow(APIRequestError);
    });
  });
});
