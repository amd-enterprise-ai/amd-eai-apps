// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { NextRequest } from 'next/server';

import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  GET,
  POST,
} from '@/app/api/projects/[project]/models/[modelId]/profiles/route';

const mockAuthenticateRoute = vi.fn();
const mockHandleError = vi.fn();
const mockProxyRequest = vi.fn();

vi.mock('@amdenterpriseai/utils/server', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@amdenterpriseai/utils/server')>();
  return {
    ...actual,
    authenticateRoute: (...args: unknown[]) => mockAuthenticateRoute(...args),
    handleError: (...args: unknown[]) => mockHandleError(...args),
    proxyRequest: (...args: unknown[]) => mockProxyRequest(...args),
  };
});

const MOCK_API_SERVICE_URL = 'https://api.example.com';
const MOCK_ACCESS_TOKEN = 'mock-access-token';

beforeEach(() => {
  vi.stubEnv('AIRM_API_SERVICE_URL', MOCK_API_SERVICE_URL);
  mockAuthenticateRoute.mockResolvedValue({ accessToken: MOCK_ACCESS_TOKEN });
  mockProxyRequest.mockResolvedValue({ data: [] });
  mockHandleError.mockImplementation((error: any) =>
    Response.json({ error: error.message }, { status: error.status || 500 }),
  );
});

describe('/api/projects/{project}/models/{modelId}/profiles', () => {
  it('GET proxies to the upstream nested profiles endpoint', async () => {
    const req = new NextRequest(
      new URL(
        '/api/projects/workbench/models/my-model-id/profiles',
        'http://localhost:3000',
      ),
      { method: 'GET' },
    );
    const response = await GET(req);

    expect(await response.json()).toEqual({ data: [] });
    expect(mockProxyRequest).toHaveBeenCalledWith(
      req,
      `${MOCK_API_SERVICE_URL}/v1/projects/workbench/models/my-model-id/profiles`,
      MOCK_ACCESS_TOKEN,
    );
  });

  it('GET forwards a URL-encoded model id unchanged', async () => {
    // The service layer encodes the repository id, which contains a slash.
    const req = new NextRequest(
      new URL(
        '/api/projects/workbench/models/meta-llama%2FLlama-3/profiles',
        'http://localhost:3000',
      ),
      { method: 'GET' },
    );
    await GET(req);

    expect(mockProxyRequest).toHaveBeenCalledWith(
      req,
      `${MOCK_API_SERVICE_URL}/v1/projects/workbench/models/meta-llama%2FLlama-3/profiles`,
      MOCK_ACCESS_TOKEN,
    );
  });

  it('GET rejects a model segment containing encoded whitespace', async () => {
    const req = new NextRequest(
      new URL(
        '/api/projects/workbench/models/my model/profiles',
        'http://localhost:3000',
      ),
      { method: 'GET' },
    );
    await GET(req);

    expect(mockProxyRequest).not.toHaveBeenCalled();
    expect(mockHandleError).toHaveBeenCalled();
  });

  it('POST proxies the create request to the same upstream collection', async () => {
    mockProxyRequest.mockResolvedValueOnce({ name: 'high-speed-7f3b6c8e' });
    const req = new NextRequest(
      new URL(
        '/api/projects/workbench/models/my-model-id/profiles',
        'http://localhost:3000',
      ),
      {
        method: 'POST',
        body: JSON.stringify({ displayName: 'High speed' }),
        headers: { 'Content-Type': 'application/json' },
      },
    );
    const response = await POST(req);

    expect(await response.json()).toEqual({ name: 'high-speed-7f3b6c8e' });
    expect(mockProxyRequest).toHaveBeenCalledWith(
      req,
      `${MOCK_API_SERVICE_URL}/v1/projects/workbench/models/my-model-id/profiles`,
      MOCK_ACCESS_TOKEN,
    );
  });
});
