// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { NextRequest } from 'next/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  DELETE,
  GET,
} from '@/app/api/projects/[project]/artifacts/[name]/route';

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
const TARGET_URL = `${API_SERVICE_URL}/v1/projects/my-project/artifacts/my-adapter`;

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubEnv('AIRM_API_SERVICE_URL', API_SERVICE_URL);
  mockAuthenticateRoute.mockResolvedValue({ accessToken: ACCESS_TOKEN });
  mockProxyRequest.mockResolvedValue({});
});

describe('/api/projects/{project}/artifacts/{name}', () => {
  it.each([
    ['GET', GET],
    ['DELETE', DELETE],
  ])('proxies %s for a registered adapter', async (method, handler) => {
    const request = new NextRequest(
      'http://localhost:3000/api/projects/my-project/artifacts/my-adapter',
      { method },
    );

    await handler(request);

    expect(mockProxyRequest).toHaveBeenCalledWith(
      request,
      TARGET_URL,
      ACCESS_TOKEN,
    );
  });
});
