// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { getServerSession } from 'next-auth';

import { describe, expect, it, vi } from 'vitest';

import { resetOidcDiscovery } from '@amdenterpriseai/utils/server';

vi.mock('next-auth');

// The setup file sets OIDC_ISSUER=https://auth.example.com/,
// OIDC_ISSUER_INTERNAL_URL=http://dex.dex.svc:5556 and
// OIDC_CLIENT_ID=oidc_client_id.
const DISCOVERY_URL =
  'http://dex.dex.svc:5556/.well-known/openid-configuration';
const LOGOUT_ENDPOINT =
  'https://auth.example.com/protocol/openid-connect/logout';
const DISCOVERY = {
  issuer: 'https://auth.example.com',
  authorization_endpoint: 'https://auth.example.com/auth',
  token_endpoint: 'https://auth.example.com/token',
  jwks_uri: 'https://auth.example.com/keys',
  end_session_endpoint: LOGOUT_ENDPOINT,
};

/** A fetch mock that answers discovery, or fails when `discovery` is an Error. */
function mockFetch(discovery: object | Error) {
  global.fetch = vi.fn(async (url: string | URL) => {
    if (String(url) !== DISCOVERY_URL) throw new Error(`unexpected ${url}`);
    if (discovery instanceof Error) throw discovery;
    return { ok: true, json: async () => discovery };
  }) as any;
}

/**
 * Runs an action that waits for the discovery retries, with the delays run by
 * fake timers, so a failing discovery costs the suite no wall clock time.
 */
function withoutRetryDelays<T>(action: () => Promise<T>): Promise<T> {
  vi.useFakeTimers();
  const result = action();
  result.catch(() => undefined);
  return vi
    .runAllTimersAsync()
    .then(() => result)
    .finally(() => vi.useRealTimers());
}

describe('logoutHandler', () => {
  let logout: () => Promise<Response>;
  const originalFetch = global.fetch;

  beforeEach(async () => {
    vi.stubEnv('NEXTAUTH_URL', 'http://localhost');

    mockFetch(DISCOVERY);
    resetOidcDiscovery();

    logout = (await import('@/app/api/auth/logout/route')).POST;
  });

  afterEach(() => {
    global.fetch = originalFetch;
    vi.resetAllMocks();
  });

  it('should return the issuer logout URL with client_id when the session has no id token', async () => {
    const res = await logout();

    expect(res.status).toBe(200);
    expect(await res.json()).toStrictEqual({
      path: `${LOGOUT_ENDPOINT}?post_logout_redirect_uri=http%3A%2F%2Flocalhost&client_id=oidc_client_id`,
    });
  });

  it('should return the issuer logout URL with id_token_hint when the session has an id token', async () => {
    vi.mocked(getServerSession).mockResolvedValueOnce({ idToken: 'id-token' });

    const res = await logout();

    expect(res.status).toBe(200);
    expect(await res.json()).toStrictEqual({
      path: `${LOGOUT_ENDPOINT}?post_logout_redirect_uri=http%3A%2F%2Flocalhost&id_token_hint=id-token`,
    });
  });

  it('should return the app URL when OIDC discovery fails', async () => {
    mockFetch(new Error('connection refused'));
    resetOidcDiscovery();

    const res = await withoutRetryDelays(() => logout());

    expect(res.status).toBe(200);
    expect(await res.json()).toStrictEqual({ path: 'http://localhost' });
  });

  it("should return a 500 status code with a JSON object containing an 'error' property when NEXTAUTH_URL environment variable is not set", async () => {
    process.env.NEXTAUTH_URL = '';

    const res = await logout();

    expect(res.status).toBe(500);
    expect(await res.json()).toStrictEqual({
      error: 'NEXTAUTH_URL is not set',
    });

    delete process.env.NEXTAUTH_URL;
  });
});
