// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { NextAuthOptions } from 'next-auth';
import { JWT } from 'next-auth/jwt';
import { OAuthConfig } from 'next-auth/providers/oauth';

import getLogger from './logger';

import jsonwebtoken, { JwtPayload } from 'jsonwebtoken';

const logger = getLogger();

/**
 * Any OIDC issuer works. The OIDC_* variables are the generic names. The
 * KEYCLOAK_* names are accepted as a fallback for one release.
 */
function envWithFallback(name: string, fallback: string): string | undefined {
  return process.env[name] || process.env[fallback];
}

// todo: check these in a different way so we don't have to set them during building the docker image
if (!process.env.NEXTAUTH_SECRET) throw new Error('NEXTAUTH_SECRET is not set');
if (!envWithFallback('OIDC_CLIENT_ID', 'KEYCLOAK_ID'))
  throw new Error('OIDC_CLIENT_ID is not set');
if (!envWithFallback('OIDC_CLIENT_SECRET', 'KEYCLOAK_SECRET'))
  throw new Error('OIDC_CLIENT_SECRET is not set');
if (!envWithFallback('OIDC_ISSUER', 'KEYCLOAK_ISSUER'))
  throw new Error('OIDC_ISSUER is not set');

const trimSlashes = (url: string) => url.replace(/\/+$/, '');

const nextAuthSecret = process.env.NEXTAUTH_SECRET;
const clientId = envWithFallback('OIDC_CLIENT_ID', 'KEYCLOAK_ID') as string;
const clientSecret = envWithFallback(
  'OIDC_CLIENT_SECRET',
  'KEYCLOAK_SECRET',
) as string;
// The public issuer: the browser goes there, and the tokens carry it as `iss`.
const issuer = trimSlashes(
  envWithFallback('OIDC_ISSUER', 'KEYCLOAK_ISSUER') as string,
);
// The issuer as the UI Pod reaches it. On a cluster the public name goes
// through the gateway, which the Pod may not reach, so the token, userinfo and
// JWKS calls use this one.
const issuerInternal = trimSlashes(
  envWithFallback('OIDC_ISSUER_INTERNAL_URL', 'KEYCLOAK_ISSUER_INTERNAL_URL') ||
    issuer,
);
const scopes = process.env.OIDC_SCOPES || 'openid profile email';

export interface OidcEndpoints {
  authorization_endpoint: string;
  token_endpoint: string;
  userinfo_endpoint?: string;
  jwks_uri: string;
  end_session_endpoint?: string;
}

/**
 * Replaces the public issuer prefix of a URL with the internal one. The URL
 * must be the issuer itself or a path under it: a host or a path that only
 * starts with the same characters is another place and stays as it is.
 */
export function toInternalUrl(
  url: string,
  publicIssuer: string,
  internalIssuer: string,
): string {
  const base = trimSlashes(publicIssuer);
  const underIssuer = url === base || url.startsWith(`${base}/`);
  return underIssuer
    ? trimSlashes(internalIssuer) + url.slice(base.length)
    : url;
}

let discovery: Promise<OidcEndpoints> | undefined;

const DISCOVERY_RETRY_DELAYS_MS = [250, 1000];

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Rejects a discovery document of another issuer, as OpenID Connect Discovery
 * requires, and one without the endpoints the login needs. The document comes
 * from the internal URL, so this is the only check that it belongs to the
 * issuer the tokens name.
 */
function checkDiscoveryDocument(doc: Record<string, unknown>, url: string) {
  if (typeof doc.issuer !== 'string' || trimSlashes(doc.issuer) !== issuer) {
    throw new Error(
      `OIDC discovery document from ${url} names the issuer ${doc.issuer}, ` +
        `but OIDC_ISSUER is ${issuer}`,
    );
  }
  for (const field of [
    'authorization_endpoint',
    'token_endpoint',
    'jwks_uri',
  ]) {
    if (typeof doc[field] !== 'string') {
      throw new Error(`OIDC discovery document from ${url} has no ${field}`);
    }
  }
}

async function fetchDiscoveryOnce(): Promise<OidcEndpoints> {
  const url = `${issuerInternal}/.well-known/openid-configuration`;
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`OIDC discovery failed: ${response.status} from ${url}`);
  }
  const doc = await response.json();
  checkDiscoveryDocument(doc, url);
  const internal = (endpoint: string, name: string): string => {
    const rewritten = toInternalUrl(endpoint, issuer, issuerInternal);
    if (rewritten === endpoint && !endpoint.startsWith(issuerInternal)) {
      logger.warn(
        `OIDC discovery gave ${name} as ${endpoint}, which is not under the ` +
          `issuer ${issuer}. The Pod calls it as it is.`,
      );
    }
    return rewritten;
  };
  return {
    authorization_endpoint: doc.authorization_endpoint,
    token_endpoint: internal(doc.token_endpoint, 'token_endpoint'),
    userinfo_endpoint: doc.userinfo_endpoint
      ? internal(doc.userinfo_endpoint, 'userinfo_endpoint')
      : undefined,
    jwks_uri: internal(doc.jwks_uri, 'jwks_uri'),
    end_session_endpoint: doc.end_session_endpoint,
  };
}

/** Retries the discovery fetch, because the issuer may be slow to answer. */
async function fetchDiscovery(): Promise<OidcEndpoints> {
  for (const delay of DISCOVERY_RETRY_DELAYS_MS) {
    try {
      return await fetchDiscoveryOnce();
    } catch (error) {
      logger.warn(`OIDC discovery attempt failed, retrying: ${error}`);
      await sleep(delay);
    }
  }
  return fetchDiscoveryOnce();
}

/**
 * The discovery document of the issuer, fetched on first use and cached. A
 * failed fetch is not cached, so the issuer may start after the UI.
 */
export function discoverOidc(): Promise<OidcEndpoints> {
  if (!discovery) {
    discovery = fetchDiscovery().catch((error) => {
      discovery = undefined;
      throw error;
    });
  }
  return discovery;
}

export function resetOidcDiscovery(): void {
  discovery = undefined;
}

interface OidcProfile {
  sub: string;
  email?: string;
  email_verified?: boolean;
  name?: string;
  preferred_username?: string;
  picture?: string;
}

function oidcProvider(endpoints?: OidcEndpoints): OAuthConfig<OidcProfile> {
  const endpointConfig = endpoints
    ? {
        authorization: {
          url: endpoints.authorization_endpoint,
          params: { scope: scopes },
        },
        token: endpoints.token_endpoint,
        userinfo: endpoints.userinfo_endpoint,
        jwks_endpoint: endpoints.jwks_uri,
      }
    : {
        wellKnown: `${issuerInternal}/.well-known/openid-configuration`,
        authorization: { params: { scope: scopes } },
      };
  return {
    id: 'oidc',
    name: 'OIDC',
    type: 'oauth',
    issuer,
    clientId,
    clientSecret,
    idToken: true,
    checks: ['pkce', 'state', 'nonce'],
    allowDangerousEmailAccountLinking: true,
    ...endpointConfig,
    profile(profile) {
      return {
        id: profile.sub,
        name: profile.name ?? profile.preferred_username ?? profile.email,
        email: profile.email,
        image: profile.picture,
        roles: [],
      };
    },
  };
}

/**
 * Takes a token, and returns a new token with updated
 * `accessToken` and `accessTokenExpires`. If an error occurs,
 * returns the old token and an error property
 * v3 docs: https://next-auth.js.org/v3/tutorials/refresh-token-rotation
 * https://authjs.dev/guides/basics/refresh-token-rotation?frameworks=core
 */
async function refreshAccessToken(token: JWT) {
  try {
    const { token_endpoint } = await discoverOidc();
    const refreshToken =
      typeof token.refreshToken === 'string' ? token.refreshToken : '';

    const params = new URLSearchParams({
      client_id: clientId,
      client_secret: clientSecret,
      grant_type: 'refresh_token',
      refresh_token: refreshToken,
    });

    const response = await fetch(token_endpoint, {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: params,
      method: 'POST',
    });

    const refreshedTokens = await response.json();

    if (!response.ok) {
      throw refreshedTokens;
    }

    const expiresAt = Date.now() + refreshedTokens.expires_in * 1000;
    return {
      ...token, // keep the previous token properties
      accessToken: refreshedTokens.access_token,
      accessTokenExpires: expiresAt,
      accessTokenExpiresHumanReadable: new Date(expiresAt).toLocaleString(),
      refreshToken: refreshedTokens.refresh_token ?? token.refreshToken, // Fall back to old refresh token
    };
  } catch (error) {
    logger.warn(`Token refresh failed: ${error}`);

    return {
      ...token,
      error: 'RefreshAccessTokenError',
    };
  }
}

export function signInLogic(
  accountProvider: string | undefined,
  profileEmail: string | undefined,
  profileEmailVerified: boolean,
) {
  if (accountProvider === 'oidc' && profileEmail && profileEmailVerified) {
    logger.debug('signIn account: ' + profileEmail);

    // profile email must be verified.
    return profileEmailVerified;
  }
  return false;
}

/**
 * The RP-initiated logout URL of the issuer, or undefined when the issuer
 * has no end session endpoint.
 */
export async function endSessionUrl(
  idToken?: string,
): Promise<string | undefined> {
  const NEXTAUTH_URL = process.env.NEXTAUTH_URL;
  if (!NEXTAUTH_URL) {
    throw new Error('NEXTAUTH_URL is not set');
  }
  const { end_session_endpoint } = await discoverOidc();
  if (!end_session_endpoint) return undefined;

  const url = new URL(end_session_endpoint);
  url.searchParams.set('post_logout_redirect_uri', NEXTAUTH_URL);
  if (idToken) {
    url.searchParams.set('id_token_hint', idToken);
  } else {
    url.searchParams.set('client_id', clientId);
  }
  return url.toString();
}

/**
 * Where the browser goes after the NextAuth session ends: the issuer logout
 * when the issuer has one, else the app itself.
 */
export async function logOutUrl(idToken?: string): Promise<string> {
  const NEXTAUTH_URL = process.env.NEXTAUTH_URL;
  if (!NEXTAUTH_URL) {
    throw new Error('NEXTAUTH_URL is not set');
  }
  try {
    return (await endSessionUrl(idToken)) ?? NEXTAUTH_URL;
  } catch (error) {
    logger.warn(
      `OIDC discovery failed on logout, the session ends locally: ${error}`,
    );
    return NEXTAUTH_URL;
  }
}

export const authOptions: NextAuthOptions = {
  secret: nextAuthSecret,
  session: {
    strategy: 'jwt',
    maxAge: 8 * 60 * 60, // 8 hours
  },
  providers: [oidcProvider()],
  debug: false,
  theme: {
    colorScheme: 'dark',
    logo: 'https://www.amd.com/content/dam/code/images/header/amd-header-logo.svg',
    brandColor: '#232341',
  },
  callbacks: {
    // restrict access to a certain domain
    async signIn({ account, profile }) {
      const canLogin = signInLogic(
        account?.provider,
        profile?.email,
        // @ts-expect-error todo email_verified is not in the type
        profile?.email_verified,
      );

      if (!canLogin) {
        // user cannot login, end the issuer session too
        logger.warn(
          'signIn account: ' + profile?.email + ' is not allowed to login.',
        );
        try {
          const url = await endSessionUrl(account?.id_token);
          if (url) await fetch(url);
        } catch (error) {
          logger.warn(
            `Could not end the issuer session of a denied login: ${error}`,
          );
        }
      }

      return canLogin;
    },
    // get the id_token from the issuer and add it to the session
    async jwt({ token, account, trigger, session }) {
      if (account) {
        // Initial sign in (account is set)
        const expiresAtHumanReadable = account.expires_at
          ? new Date(account.expires_at * 1000).toLocaleString()
          : '';
        token = Object.assign({}, token, {
          idToken: account.id_token,
          accessToken: account.access_token,
          accessTokenExpires: account.expires_at
            ? account.expires_at * 1000
            : undefined,
          accessTokenExpiresHumanReadable: expiresAtHumanReadable,
          refreshToken: account.refresh_token,
        });
        return token;
      } else if (trigger === 'update') {
        const updatedToken: JWT = await refreshAccessToken(token);
        if (updatedToken.error === 'RefreshAccessTokenError') {
          throw new Error('RefreshTokenExpired');
        }
        logger.debug('Token refreshed via update trigger');
        return updatedToken;
      } else if (Date.now() < (token.accessTokenExpires as number)) {
        // Return previous token if the access token has not expired yet
        return token;
      } else {
        // Access token has expired, try to update it
        const updatedToken: JWT = await refreshAccessToken(token);
        if (updatedToken.error === 'RefreshAccessTokenError') {
          // If the refresh token has expired, throw an error to sign the user out
          logger.warn('RefreshTokenExpired');
          throw new Error('RefreshTokenExpired');
        }
        logger.debug('Token refreshed');
        return updatedToken;
      }
    },
    async session({ session, user, token }) {
      const decoded = jsonwebtoken.decode(
        token.accessToken as string,
      ) as JwtPayload;
      const roles = decoded?.realm_access?.roles || [];

      if (session) {
        session = Object.assign({}, session, {
          idToken: token.idToken,
          accessToken: token.accessToken,
          error: token.error,
          user: { ...session.user, roles },
        });
      }
      return session;
    },
  },
};

/**
 * The options for the NextAuth route handler. The provider gets the
 * endpoints from discovery, with the back-channel ones on the internal URL.
 * `authOptions` is enough for getServerSession, which reads the cookie only.
 */
export async function getAuthOptions(): Promise<NextAuthOptions> {
  const endpoints = await discoverOidc();
  return { ...authOptions, providers: [oidcProvider(endpoints)] };
}
