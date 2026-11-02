// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { NextRequest } from 'next/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { GET } from '@/app/api/projects/[project]/artifacts/route';

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

const API_SERVICE_URL = 'https://api.example.com';
const ACCESS_TOKEN = 'mock-access-token';

beforeEach(() => {
  vi.stubEnv('AIRM_API_SERVICE_URL', API_SERVICE_URL);
  mockAuthenticateRoute.mockResolvedValue({ accessToken: ACCESS_TOKEN });
  mockProxyRequest.mockResolvedValue({ data: [] });
});

describe('GET /api/projects/{project}/artifacts', () => {
  it('proxies the project adapter list with its query parameters', async () => {
    const request = new NextRequest(
      'http://localhost:3000/api/projects/my-project/artifacts?page=2&pageSize=25',
    );

    await GET(request);

    expect(mockProxyRequest).toHaveBeenCalledWith(
      request,
      `${API_SERVICE_URL}/v1/projects/my-project/artifacts`,
      ACCESS_TOKEN,
    );
  });
});
