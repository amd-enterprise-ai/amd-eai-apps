// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  createApiKey,
  deleteApiKey,
  fetchProjectApiKeys,
} from '@/lib/app/api-keys';

import { APIRequestError } from '@amdenterpriseai/utils/app';

import {
  generateMockApiKeyResponse,
  generateMockCreateApiKeyData,
  generateMockFullApiKey,
} from '@/__mocks__/utils/api-keys-mock';

// Mock the typed apiClient (not globalThis.fetch): the service layer awaits an
// openapi-fetch `{ data, error, response }` envelope from each verb.
const mockGET = vi.fn();
const mockPOST = vi.fn();
const mockDELETE = vi.fn();
const mockPATCH = vi.fn();

vi.mock('@/lib/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api-client')>();
  return {
    ...actual,
    apiClient: {
      GET: (...args: unknown[]) => mockGET(...args),
      POST: (...args: unknown[]) => mockPOST(...args),
      DELETE: (...args: unknown[]) => mockDELETE(...args),
      PATCH: (...args: unknown[]) => mockPATCH(...args),
    },
  };
});

beforeEach(() => {
  vi.clearAllMocks();
});

describe('api-keys service', () => {
  describe('fetchProjectApiKeys', () => {
    it('should fetch a single page when total fits in one page', async () => {
      const mockResponse = generateMockApiKeyResponse();
      mockGET.mockResolvedValue({
        data: {
          data: mockResponse.data,
          pagination: {
            page: 1,
            pageSize: 100,
            total: mockResponse.data.length,
          },
        },
        error: undefined,
        response: { status: 200 } as Response,
      });

      const result = await fetchProjectApiKeys('project-1');

      expect(mockGET).toHaveBeenCalledTimes(1);
      expect(mockGET).toHaveBeenCalledWith('/api/projects/{project}/api-keys', {
        params: {
          path: { project: 'project-1' },
          query: { page: 1, pageSize: 100 },
        },
      });
      expect(result).toEqual({ data: mockResponse.data });
    });

    it('should walk every page when total exceeds one page', async () => {
      // Backend caps pageSize at 100; with total=250 the loader must issue
      // requests for page 1, 2, and 3 and concatenate the results.
      const pageOne = Array.from({ length: 100 }, (_, i) => ({ id: `k-${i}` }));
      const pageTwo = Array.from({ length: 100 }, (_, i) => ({
        id: `k-${100 + i}`,
      }));
      const pageThree = Array.from({ length: 50 }, (_, i) => ({
        id: `k-${200 + i}`,
      }));

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

      const result = await fetchProjectApiKeys('project-1');

      expect(mockGET).toHaveBeenCalledTimes(3);
      expect(result.data).toHaveLength(250);
      expect(result.data[0]).toEqual({ id: 'k-0' });
      expect(result.data[249]).toEqual({ id: 'k-249' });
    });

    it('should handle fetch error', async () => {
      // Mirror the BFF handleError() response shape: it flattens the upstream
      // detail into a top-level `error` field, which is what getApiClientErrorMessage reads.
      mockGET.mockResolvedValue({
        data: undefined,
        error: { detail: 'boom', error: 'boom' },
        response: {
          status: 500,
          statusText: 'Internal Server Error',
        } as Response,
      });

      await expect(fetchProjectApiKeys('project-1')).rejects.toThrow(/boom/);

      expect(mockGET).toHaveBeenCalledTimes(1);
    });

    it('should handle empty API keys list', async () => {
      mockGET.mockResolvedValue({
        data: { data: [], pagination: { page: 1, pageSize: 100, total: 0 } },
        error: undefined,
        response: { status: 200 } as Response,
      });

      const result = await fetchProjectApiKeys('project-1');

      expect(mockGET).toHaveBeenCalledTimes(1);
      expect(result).toEqual({ data: [] });
    });
  });

  describe('deleteApiKey', () => {
    it('should delete API key successfully', async () => {
      mockDELETE.mockResolvedValue({
        error: undefined,
        response: { status: 204, ok: true } as Response,
      });

      await deleteApiKey('project-1', 'api-key-1');

      expect(mockDELETE).toHaveBeenCalledWith(
        '/api/projects/{project}/api-keys/{api_key_id}',
        { params: { path: { project: 'project-1', api_key_id: 'api-key-1' } } },
      );
    });

    it('should handle delete error', async () => {
      mockDELETE.mockResolvedValue({
        error: { detail: 'not found', error: 'not found' },
        response: {
          ok: false,
          status: 404,
          statusText: 'Not Found',
        } as Response,
      });

      await expect(deleteApiKey('project-1', 'api-key-1')).rejects.toThrow(
        /not found/,
      );
    });
  });

  describe('createApiKey', () => {
    it('should create API key successfully', async () => {
      const mockResponse = generateMockFullApiKey();
      mockPOST.mockResolvedValue({
        data: mockResponse,
        error: undefined,
        response: { status: 201 } as Response,
      });

      const createData = generateMockCreateApiKeyData();
      const result = await createApiKey('project-1', createData);

      expect(mockPOST).toHaveBeenCalledWith(
        '/api/projects/{project}/api-keys',
        {
          params: { path: { project: 'project-1' } },
          body: createData,
        },
      );
      expect(result).toEqual(mockResponse);
    });

    it('should handle create error', async () => {
      mockPOST.mockResolvedValue({
        data: undefined,
        error: { detail: 'bad request', error: 'bad request' },
        response: { status: 400, statusText: 'Bad Request' } as Response,
      });

      const createData = generateMockCreateApiKeyData();
      await expect(createApiKey('project-1', createData)).rejects.toThrow(
        /bad request/,
      );
    });

    it('should include the request body', async () => {
      mockPOST.mockResolvedValue({
        data: generateMockFullApiKey(),
        error: undefined,
        response: { status: 201 } as Response,
      });

      const createData = generateMockCreateApiKeyData();
      await createApiKey('project-1', createData);

      expect(mockPOST).toHaveBeenCalledWith(
        '/api/projects/{project}/api-keys',
        expect.objectContaining({ body: createData }),
      );
    });
  });
});
