// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  signInLogic,
  logOutUrl,
  endSessionUrl,
  authOptions,
  getAuthOptions,
  discoverOidc,
  resetOidcDiscovery,
  toInternalUrl,
} from '@amdenterpriseai/utils/server';
import jsonwebtoken from 'jsonwebtoken';

// The setup file sets OIDC_ISSUER=https://auth.example.com/ and
// OIDC_ISSUER_INTERNAL_URL=http://dex.dex.svc:5556.
const DISCOVERY_URL =
  'http://dex.dex.svc:5556/.well-known/openid-configuration';

const dexDiscovery = {
  issuer: 'https://auth.example.com',
  authorization_endpoint: 'https://auth.example.com/auth',
  token_endpoint: 'https://auth.example.com/token',
  userinfo_endpoint: 'https://auth.example.com/userinfo',
  jwks_uri: 'https://auth.example.com/keys',
};

const keycloakDiscovery = {
  ...dexDiscovery,
  end_session_endpoint:
    'https://auth.example.com/protocol/openid-connect/logout',
};

/** A fetch mock that answers discovery and hands other calls to `other`. */
function mockFetch(
  discovery: object | Error = dexDiscovery,
  other: (url: string) => object = () => ({ ok: true, json: async () => ({}) }),
) {
  const fn = vi.fn(async (url: string | URL) => {
    if (String(url) === DISCOVERY_URL) {
      if (discovery instanceof Error) throw discovery;
      return { ok: true, json: async () => discovery };
    }
    return other(String(url));
  });
  global.fetch = fn as any;
  return fn;
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

describe('signInLogic', () => {
  it('should return true for a verified oidc account', () => {
    expect(signInLogic('oidc', 'user@example.com', true)).toBe(true);
  });

  it('should return false for any other provider', () => {
    expect(signInLogic('keycloak', 'user@example.com', true)).toBe(false);
    expect(signInLogic('github', 'user@example.com', true)).toBe(false);
    expect(signInLogic(undefined, 'user@example.com', true)).toBe(false);
  });

  it('should return false without an email or without verification', () => {
    expect(signInLogic('oidc', undefined, true)).toBe(false);
    expect(signInLogic('oidc', '', true)).toBe(false);
    expect(signInLogic('oidc', 'user@example.com', false)).toBe(false);
  });
});

describe('toInternalUrl', () => {
  it('should replace the public issuer prefix with the internal one', () => {
    expect(
      toInternalUrl(
        'https://auth.example.com/token',
        'https://auth.example.com/',
        'http://dex.dex.svc:5556/',
      ),
    ).toBe('http://dex.dex.svc:5556/token');
  });

  it('should keep a realm path after the prefix', () => {
    expect(
      toInternalUrl(
        'https://kc.example.com/realms/airm/protocol/openid-connect/certs',
        'https://kc.example.com/realms/airm',
        'http://keycloak.keycloak.svc:8080/realms/airm/',
      ),
    ).toBe(
      'http://keycloak.keycloak.svc:8080/realms/airm/protocol/openid-connect/certs',
    );
  });

  it('should leave a URL on another host unchanged', () => {
    expect(
      toInternalUrl(
        'https://cdn.example.com/keys',
        'https://auth.example.com',
        'http://dex',
      ),
    ).toBe('https://cdn.example.com/keys');
  });

  it('should leave a host that only starts with the issuer host unchanged', () => {
    expect(
      toInternalUrl(
        'https://auth.example.com.attacker.net/token',
        'https://auth.example.com',
        'https://internal.svc.cluster.local',
      ),
    ).toBe('https://auth.example.com.attacker.net/token');
  });

  it('should leave a path that only starts with the issuer path unchanged', () => {
    expect(
      toInternalUrl(
        'https://kc.example.com/realms/airm-old/certs',
        'https://kc.example.com/realms/airm',
        'http://keycloak.keycloak.svc:8080/realms/airm',
      ),
    ).toBe('https://kc.example.com/realms/airm-old/certs');
  });

  it('should replace the issuer itself', () => {
    expect(
      toInternalUrl(
        'https://auth.example.com',
        'https://auth.example.com/',
        'http://dex.dex.svc:5556',
      ),
    ).toBe('http://dex.dex.svc:5556');
  });
});

describe('discoverOidc', () => {
  const originalFetch = global.fetch;

  beforeEach(() => resetOidcDiscovery());
  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it('should rewrite the back-channel endpoints and keep the authorization one', async () => {
    mockFetch();

    const endpoints = await discoverOidc();

    expect(endpoints.authorization_endpoint).toBe(
      'https://auth.example.com/auth',
    );
    expect(endpoints.token_endpoint).toBe('http://dex.dex.svc:5556/token');
    expect(endpoints.userinfo_endpoint).toBe(
      'http://dex.dex.svc:5556/userinfo',
    );
    expect(endpoints.jwks_uri).toBe('http://dex.dex.svc:5556/keys');
    expect(endpoints.end_session_endpoint).toBeUndefined();
  });

  it('should fetch the document once', async () => {
    const fetchMock = mockFetch();

    await discoverOidc();
    await discoverOidc();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith(DISCOVERY_URL);
  });

  it('should not cache a failed fetch', async () => {
    const fetchMock = mockFetch(new Error('connection refused'));
    await expect(withoutRetryDelays(discoverOidc)).rejects.toThrow(
      'connection refused',
    );

    mockFetch();
    await expect(discoverOidc()).resolves.toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it('should retry until the issuer answers', async () => {
    let attempts = 0;
    const fetchMock = vi.fn(async () => {
      attempts += 1;
      if (attempts < 3) throw new Error('connection refused');
      return { ok: true, json: async () => dexDiscovery };
    });
    global.fetch = fetchMock as any;

    const endpoints = await withoutRetryDelays(discoverOidc);

    expect(endpoints.jwks_uri).toBe('http://dex.dex.svc:5556/keys');
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it('should fail on a non-200 answer', async () => {
    global.fetch = vi.fn(async () => ({ ok: false, status: 503 })) as any;

    await expect(withoutRetryDelays(discoverOidc)).rejects.toThrow(
      'OIDC discovery failed: 503',
    );
  });

  it('should fail on a document without a token endpoint', async () => {
    const { token_endpoint: _, ...doc } = dexDiscovery;
    mockFetch(doc);

    await expect(withoutRetryDelays(discoverOidc)).rejects.toThrow(
      'has no token_endpoint',
    );
  });

  it('should fail on a document of another issuer', async () => {
    mockFetch({ ...dexDiscovery, issuer: 'https://other.example.com' });

    await expect(withoutRetryDelays(discoverOidc)).rejects.toThrow(
      'names the issuer https://other.example.com, but OIDC_ISSUER is https://auth.example.com',
    );
  });

  it('should fail on a document without an issuer', async () => {
    const { issuer: _, ...doc } = dexDiscovery;
    mockFetch(doc);

    await expect(withoutRetryDelays(discoverOidc)).rejects.toThrow(
      'names the issuer undefined',
    );
  });

  it('should accept an issuer with a trailing slash', async () => {
    mockFetch({ ...dexDiscovery, issuer: 'https://auth.example.com/' });

    const endpoints = await discoverOidc();

    expect(endpoints.token_endpoint).toBe('http://dex.dex.svc:5556/token');
  });
});

describe('logOutUrl', () => {
  const originalEnv = process.env;
  const originalFetch = global.fetch;

  beforeEach(() => {
    process.env = { ...originalEnv };
    process.env.NEXTAUTH_URL = 'http://localhost:3000';
    resetOidcDiscovery();
  });

  afterEach(() => {
    process.env = originalEnv;
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it('should build the end session URL with id_token_hint', async () => {
    mockFetch(keycloakDiscovery);

    const url = new URL(await logOutUrl('test-id-token-123'));

    expect(url.origin + url.pathname).toBe(
      'https://auth.example.com/protocol/openid-connect/logout',
    );
    expect(url.searchParams.get('post_logout_redirect_uri')).toBe(
      'http://localhost:3000',
    );
    expect(url.searchParams.get('id_token_hint')).toBe('test-id-token-123');
    expect(url.searchParams.has('client_id')).toBe(false);
  });

  it('should build the end session URL with client_id when there is no id token', async () => {
    mockFetch(keycloakDiscovery);

    const url = new URL(await logOutUrl());

    expect(url.searchParams.get('client_id')).toBe('oidc_client_id');
    expect(url.searchParams.has('id_token_hint')).toBe(false);
  });

  it('should encode a redirect URI with special characters', async () => {
    mockFetch(keycloakDiscovery);
    process.env.NEXTAUTH_URL = 'https://example.com/app?test=value';

    const url = new URL(await logOutUrl());

    expect(url.searchParams.get('post_logout_redirect_uri')).toBe(
      'https://example.com/app?test=value',
    );
  });

  it('should return the app URL when the issuer has no end session endpoint', async () => {
    mockFetch(dexDiscovery);

    expect(await logOutUrl('id-token')).toBe('http://localhost:3000');
    expect(await endSessionUrl('id-token')).toBeUndefined();
  });

  it('should return the app URL when discovery fails', async () => {
    mockFetch(new Error('connection refused'));

    expect(await withoutRetryDelays(() => logOutUrl())).toBe(
      'http://localhost:3000',
    );
  });

  it('should throw when NEXTAUTH_URL is not set', async () => {
    delete process.env.NEXTAUTH_URL;

    await expect(logOutUrl()).rejects.toThrow('NEXTAUTH_URL is not set');
    await expect(endSessionUrl()).rejects.toThrow('NEXTAUTH_URL is not set');
  });
});

describe('getAuthOptions', () => {
  const originalFetch = global.fetch;

  beforeEach(() => resetOidcDiscovery());
  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it('should ask for pkce, state and nonce', async () => {
    mockFetch();

    const options = await getAuthOptions();
    const provider = options.providers[0] as any;

    expect(provider.checks).toEqual(['pkce', 'state', 'nonce']);
  });

  it('should configure the provider with the discovered endpoints', async () => {
    mockFetch();

    const options = await getAuthOptions();
    const provider = options.providers[0] as any;

    expect(provider.id).toBe('oidc');
    expect(provider.type).toBe('oauth');
    expect(provider.issuer).toBe('https://auth.example.com');
    expect(provider.clientId).toBe('oidc_client_id');
    expect(provider.clientSecret).toBe('oidc_client_secret');
    expect(provider.authorization.url).toBe('https://auth.example.com/auth');
    expect(provider.authorization.params.scope).toBe('openid profile email');
    expect(provider.token).toBe('http://dex.dex.svc:5556/token');
    expect(provider.userinfo).toBe('http://dex.dex.svc:5556/userinfo');
    expect(provider.jwks_endpoint).toBe('http://dex.dex.svc:5556/keys');
    expect(provider.wellKnown).toBeUndefined();
    expect(options.callbacks).toBe(authOptions.callbacks);
  });

  it('should leave the static options on discovery', () => {
    const provider = authOptions.providers[0] as any;

    expect(provider.id).toBe('oidc');
    expect(provider.wellKnown).toBe(DISCOVERY_URL);
  });
});

describe('environment fallback', () => {
  it('should accept the KEYCLOAK_* names', async () => {
    vi.resetModules();
    vi.stubEnv('OIDC_CLIENT_ID', '');
    vi.stubEnv('OIDC_CLIENT_SECRET', '');
    vi.stubEnv('OIDC_ISSUER', '');
    vi.stubEnv('OIDC_ISSUER_INTERNAL_URL', '');
    vi.stubEnv('KEYCLOAK_ID', 'kc-client');
    vi.stubEnv('KEYCLOAK_SECRET', 'kc-secret');
    vi.stubEnv('KEYCLOAK_ISSUER', 'https://kc.example.com/realms/airm');
    vi.stubEnv(
      'KEYCLOAK_ISSUER_INTERNAL_URL',
      'http://keycloak.keycloak.svc:8080/realms/airm/',
    );

    const auth = await import('../../src/server/auth');
    const provider = auth.authOptions.providers[0] as any;

    expect(provider.clientId).toBe('kc-client');
    expect(provider.issuer).toBe('https://kc.example.com/realms/airm');
    expect(provider.wellKnown).toBe(
      'http://keycloak.keycloak.svc:8080/realms/airm/.well-known/openid-configuration',
    );

    vi.unstubAllEnvs();
    vi.resetModules();
  });
});

describe('authOptions callbacks', () => {
  const originalEnv = process.env;
  const originalFetch = global.fetch;

  beforeEach(() => {
    process.env = { ...originalEnv };
    process.env.NEXTAUTH_URL = 'http://localhost:3000';
    resetOidcDiscovery();
  });

  afterEach(() => {
    process.env = originalEnv;
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it('signIn should return true for a verified profile and not call the issuer', async () => {
    const fetchMock = mockFetch();

    const result = await authOptions.callbacks?.signIn?.({
      account: { provider: 'oidc', id_token: 'id-token' } as any,
      profile: { email: 'user@example.com', email_verified: true } as any,
    } as any);

    expect(result).toBe(true);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('signIn should end the issuer session when the user cannot log in', async () => {
    const fetchMock = mockFetch(keycloakDiscovery);

    const result = await authOptions.callbacks?.signIn?.({
      account: { provider: 'oidc', id_token: 'id-token' } as any,
      profile: { email: 'user@example.com', email_verified: false } as any,
    } as any);

    expect(result).toBe(false);
    const calls = fetchMock.mock.calls.map((call) => String(call[0]));
    expect(calls).toHaveLength(2);
    expect(calls[1]).toContain('/protocol/openid-connect/logout?');
    expect(calls[1]).toContain('id_token_hint=id-token');
  });

  it('signIn should only refuse when the issuer has no end session endpoint', async () => {
    const fetchMock = mockFetch(dexDiscovery);

    const result = await authOptions.callbacks?.signIn?.({
      account: { provider: 'oidc', id_token: 'id-token' } as any,
      profile: { email: 'user@example.com', email_verified: false } as any,
    } as any);

    expect(result).toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('signIn should refuse without throwing when discovery fails', async () => {
    mockFetch(new Error('connection refused'));

    const result = await withoutRetryDelays(() =>
      Promise.resolve(
        authOptions.callbacks?.signIn?.({
          account: { provider: 'oidc', id_token: 'id-token' } as any,
          profile: { email: 'user@example.com', email_verified: false } as any,
        } as any),
      ),
    );

    expect(result).toBe(false);
  });

  it('jwt should set token fields on initial sign-in', async () => {
    const account = {
      id_token: 'id-token',
      access_token: 'access-token',
      refresh_token: 'refresh-token',
      expires_at: 1700000000,
    } as any;

    const result = await authOptions.callbacks?.jwt?.({
      token: {} as any,
      account,
      trigger: undefined,
      session: undefined,
    } as any);

    expect(result?.idToken).toBe('id-token');
    expect(result?.accessToken).toBe('access-token');
    expect(result?.refreshToken).toBe('refresh-token');
    expect(result?.accessTokenExpires).toBe(1700000000 * 1000);
    expect(result?.accessTokenExpiresHumanReadable).toBeTruthy();
  });

  it('jwt should refresh the token on the update trigger through the internal token endpoint', async () => {
    const nowSpy = vi.spyOn(Date, 'now').mockReturnValue(1700000000000);
    const fetchMock = mockFetch(dexDiscovery, () => ({
      ok: true,
      json: async () => ({
        access_token: 'new-access-token',
        refresh_token: 'new-refresh-token',
        expires_in: 3600,
      }),
    }));

    const result = await authOptions.callbacks?.jwt?.({
      token: { refreshToken: 'old-refresh-token' } as any,
      account: undefined,
      trigger: 'update',
      session: undefined,
    } as any);

    expect(result?.accessToken).toBe('new-access-token');
    expect(result?.refreshToken).toBe('new-refresh-token');
    expect(result?.accessTokenExpires).toBe(1700000000000 + 3600 * 1000);
    const [url, init] = fetchMock.mock.calls[1] as any;
    expect(url).toBe('http://dex.dex.svc:5556/token');
    expect(init.method).toBe('POST');
    expect(String(init.body)).toContain('grant_type=refresh_token');
    expect(String(init.body)).toContain('client_id=oidc_client_id');

    nowSpy.mockRestore();
  });

  it('jwt should throw when the refresh fails on the update trigger', async () => {
    mockFetch(dexDiscovery, () => ({
      ok: false,
      json: async () => ({ error: 'invalid_grant' }),
    }));

    await expect(
      authOptions.callbacks?.jwt?.({
        token: { refreshToken: 'bad-refresh-token' } as any,
        account: undefined,
        trigger: 'update',
        session: undefined,
      } as any),
    ).rejects.toThrow('RefreshTokenExpired');
  });

  it('jwt should return the existing token when it has not expired', async () => {
    const nowSpy = vi.spyOn(Date, 'now').mockReturnValue(1000);
    const fetchMock = mockFetch();

    const token = { accessTokenExpires: 2000 } as any;
    const result = await authOptions.callbacks?.jwt?.({
      token,
      account: undefined,
      trigger: undefined,
      session: undefined,
    } as any);

    expect(result).toBe(token);
    expect(fetchMock).not.toHaveBeenCalled();

    nowSpy.mockRestore();
  });

  it('jwt should refresh the token when it has expired', async () => {
    const nowSpy = vi.spyOn(Date, 'now').mockReturnValue(2000);
    mockFetch(dexDiscovery, () => ({
      ok: true,
      json: async () => ({
        access_token: 'refreshed-access-token',
        refresh_token: undefined,
        expires_in: 1800,
      }),
    }));

    const token = { accessTokenExpires: 1000, refreshToken: 'refresh' } as any;
    const result = await authOptions.callbacks?.jwt?.({
      token,
      account: undefined,
      trigger: undefined,
      session: undefined,
    } as any);

    expect(result?.accessToken).toBe('refreshed-access-token');
    expect(result?.refreshToken).toBe('refresh');
    expect(result?.accessTokenExpires).toBe(2000 + 1800 * 1000);

    nowSpy.mockRestore();
  });

  it('jwt should throw when discovery fails on refresh', async () => {
    const nowSpy = vi.spyOn(Date, 'now').mockReturnValue(2000);
    mockFetch(new Error('connection refused'));

    await expect(
      withoutRetryDelays(() =>
        Promise.resolve(
          authOptions.callbacks?.jwt?.({
            token: { accessTokenExpires: 1000, refreshToken: 'refresh' } as any,
            account: undefined,
            trigger: undefined,
            session: undefined,
          } as any),
        ),
      ),
    ).rejects.toThrow('RefreshTokenExpired');

    nowSpy.mockRestore();
  });

  it('session should attach roles from the access token', async () => {
    const decodeSpy = vi
      .spyOn(jsonwebtoken, 'decode')
      .mockReturnValue({ realm_access: { roles: ['admin', 'user'] } } as any);

    const session = { user: { name: 'Test User', roles: [] } } as any;
    const token = { accessToken: 'access-token', idToken: 'id-token' } as any;

    const result = await authOptions.callbacks?.session?.({
      session,
      user: undefined,
      token,
    } as any);

    expect(result?.user.roles).toEqual(['admin', 'user']);
    expect(result?.accessToken).toBe('access-token');
    expect(result?.idToken).toBe('id-token');

    decodeSpy.mockRestore();
  });

  it('session should give an empty roles list to a token without realm roles', async () => {
    const decodeSpy = vi
      .spyOn(jsonwebtoken, 'decode')
      .mockReturnValue({ sub: 'user-1', email: 'user@example.com' } as any);

    const result = await authOptions.callbacks?.session?.({
      session: { user: { name: 'Test User' } } as any,
      user: undefined,
      token: { accessToken: 'access-token' } as any,
    } as any);

    expect(result?.user.roles).toEqual([]);

    decodeSpy.mockRestore();
  });
});
