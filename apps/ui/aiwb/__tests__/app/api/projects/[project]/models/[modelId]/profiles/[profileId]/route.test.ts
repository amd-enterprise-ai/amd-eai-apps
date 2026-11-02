// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { NextRequest } from 'next/server';

import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  DELETE,
  GET,
  PATCH,
} from '@/app/api/projects/[project]/models/[modelId]/profiles/[profileId]/route';

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
const UPSTREAM_PROFILE_URL = `${MOCK_API_SERVICE_URL}/v1/projects/workbench/models/my-model-id/profiles/profile-1`;

beforeEach(() => {
  vi.stubEnv('AIRM_API_SERVICE_URL', MOCK_API_SERVICE_URL);
  mockAuthenticateRoute.mockResolvedValue({ accessToken: MOCK_ACCESS_TOKEN });
  mockProxyRequest.mockResolvedValue({ success: true });
  mockHandleError.mockImplementation((error: any) =>
    Response.json({ error: error.message }, { status: error.status || 500 }),
  );
});

describe('/api/projects/{project}/models/{modelId}/profiles/{profileId}', () => {
  it('GET proxies to the upstream single-profile endpoint', async () => {
    const req = new NextRequest(
      new URL(
        '/api/projects/workbench/models/my-model-id/profiles/profile-1',
        'http://localhost:3000',
      ),
      { method: 'GET' },
    );
    const response = await GET(req);

    expect(await response.json()).toEqual({ success: true });
    expect(mockProxyRequest).toHaveBeenCalledWith(
      req,
      UPSTREAM_PROFILE_URL,
      MOCK_ACCESS_TOKEN,
    );
  });

  it('DELETE returns 204 with empty body when upstream has no content', async () => {
    mockProxyRequest.mockResolvedValueOnce({ status: 204 });
    const req = new NextRequest(
      new URL(
        '/api/projects/workbench/models/my-model-id/profiles/profile-1',
        'http://localhost:3000',
      ),
      { method: 'DELETE' },
    );
    const response = await DELETE(req);

    expect(response.status).toBe(204);
    expect(await response.text()).toBe('');
    expect(mockProxyRequest).toHaveBeenCalledWith(
      req,
      UPSTREAM_PROFILE_URL,
      MOCK_ACCESS_TOKEN,
    );
  });

  it('PATCH proxies the update request to the upstream single-profile endpoint', async () => {
    mockProxyRequest.mockResolvedValueOnce({ displayName: 'High speed v2' });
    const req = new NextRequest(
      new URL(
        '/api/projects/workbench/models/my-model-id/profiles/profile-1',
        'http://localhost:3000',
      ),
      {
        method: 'PATCH',
        body: JSON.stringify({ displayName: 'High speed v2' }),
        headers: { 'Content-Type': 'application/json' },
      },
    );
    const response = await PATCH(req);

    expect(await response.json()).toEqual({ displayName: 'High speed v2' });
    expect(mockProxyRequest).toHaveBeenCalledWith(
      req,
      UPSTREAM_PROFILE_URL,
      MOCK_ACCESS_TOKEN,
    );
  });

  it('DELETE forwards the reserved default literal unchanged', async () => {
    const req = new NextRequest(
      new URL(
        '/api/projects/workbench/models/my-model-id/profiles/default',
        'http://localhost:3000',
      ),
      { method: 'DELETE' },
    );
    await DELETE(req);

    expect(mockProxyRequest).toHaveBeenCalledWith(
      req,
      `${MOCK_API_SERVICE_URL}/v1/projects/workbench/models/my-model-id/profiles/default`,
      MOCK_ACCESS_TOKEN,
    );
  });
});
