// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import jsonwebtoken, { type JwtPayload } from 'jsonwebtoken';
import { NextRequest } from 'next/server';

import {
  authenticateRoute,
  handleError,
  RouteError,
} from '@amdenterpriseai/utils/server';

import type { components } from '@/types/api';
import type { ChatBody } from '@/types/chat';

import { getCachedAccess, setCachedAccess } from './authz-cache';
import { transformChatStream } from './chat-stream-transform';
import { validatePathSegments } from './proxy-handler';

type InferenceDeploymentResponse =
  components['schemas']['InferenceDeploymentResponse'];

const AIM_CHAT_PATH_REGEX =
  /^\/api\/ui\/projects\/([^/]+)\/inference\/([^/]+)\/chat$/;

type AimChatTarget = {
  project: string;
  deploymentId: string;
};

// Singleflight: collapses concurrent first-time lookups for the same
// (userId, deploymentId) into a single upstream AIWB authz request.
const inflightAuthz = new Map<string, Promise<string>>();

function parseAimChatPath(req: NextRequest): AimChatTarget {
  const match = req.nextUrl.pathname.match(AIM_CHAT_PATH_REGEX);
  if (!match) {
    throw new RouteError(400, 'Invalid AIM chat path');
  }
  const project = match[1];
  const deploymentId = match[2];
  validatePathSegments([project, deploymentId]);
  return { project, deploymentId };
}

// Decode-only (no signature verification): `authenticateRoute()` above already
// validates the token via NextAuth/Keycloak and rejects unauthenticated calls,
// so by the time we reach here the token is trusted. We only need `sub` to
// scope the authz cache per user.
function extractUserId(accessToken: string): string {
  const decoded = jsonwebtoken.decode(accessToken) as JwtPayload | null;
  const sub = decoded?.sub;
  if (!sub) {
    throw new RouteError(401, 'Unable to identify caller from access token');
  }
  return sub;
}

async function resolveInternalUrl({
  project,
  deploymentId,
  accessToken,
  signal,
}: {
  project: string;
  deploymentId: string;
  accessToken: string;
  signal: AbortSignal;
}): Promise<string> {
  const aimUrl = `${process.env.AIRM_API_SERVICE_URL}/v1/projects/${project}/inference/${deploymentId}`;
  const targetUrl = new URL(aimUrl);
  const expectedUrl = new URL(process.env.AIRM_API_SERVICE_URL as string);
  if (targetUrl.origin !== expectedUrl.origin) {
    throw new RouteError(400, 'Invalid path: URL manipulation detected');
  }
  const response = await fetch(aimUrl, {
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${accessToken}`,
    },
    method: 'GET',
    signal,
  });
  if (!response.ok) {
    const body = await response.text();
    throw new RouteError(response.status, body);
  }
  const payload = (await response.json()) as InferenceDeploymentResponse;
  const internalUrl: string | undefined = payload?.endpoints?.internal;
  if (!internalUrl) {
    throw new RouteError(422, 'AIM is not ready for chat');
  }
  return internalUrl;
}

function applyInternalUrlOverride(internalUrl: string): string {
  const override = process.env.CHAT_INTERNAL_URL_OVERRIDE;
  return override ? override : internalUrl;
}

async function getAuthorizedInternalUrl({
  project,
  deploymentId,
  accessToken,
  userId,
  signal,
}: {
  project: string;
  deploymentId: string;
  accessToken: string;
  userId: string;
  signal: AbortSignal;
}): Promise<string> {
  const cached = getCachedAccess({ userId, deploymentId });
  if (cached) {
    return applyInternalUrlOverride(cached.internalUrl);
  }
  const key = `${userId}:${deploymentId}`;
  const existing = inflightAuthz.get(key);
  if (existing) {
    const internalUrl = await existing;
    return applyInternalUrlOverride(internalUrl);
  }
  const promise = resolveInternalUrl({
    project,
    deploymentId,
    accessToken,
    signal,
  })
    .then((internalUrl) => {
      setCachedAccess({ userId, deploymentId, internalUrl });
      return internalUrl;
    })
    .finally(() => {
      inflightAuthz.delete(key);
    });
  inflightAuthz.set(key, promise);
  const internalUrl = await promise;
  return applyInternalUrlOverride(internalUrl);
}

async function aimChatHandler(req: NextRequest): Promise<Response> {
  try {
    const { project, deploymentId } = parseAimChatPath(req);
    const { accessToken } = await authenticateRoute();
    const userId = extractUserId(accessToken as string);
    // OpenAI-compatible body: snake_case fields are preserved (the /chat path is
    // the camelCase carve-out), so ChatBody keeps them as-is.
    const body = (await req.json()) as ChatBody;
    const internalUrl = await getAuthorizedInternalUrl({
      project,
      deploymentId,
      accessToken: accessToken as string,
      userId,
      signal: req.signal,
    });
    const upstream = await fetch(`${internalUrl}/v1/chat/completions`, {
      headers: { 'Content-Type': 'application/json' },
      method: 'POST',
      body: JSON.stringify(body),
      signal: req.signal,
    });
    if (upstream.status !== 200) {
      throw new RouteError(upstream.status, await upstream.text());
    }
    if (!upstream.body) {
      throw new RouteError(502, 'Response body is not readable');
    }
    return transformChatStream(upstream.body);
  } catch (error) {
    return handleError(error);
  }
}

export function POST(req: NextRequest): Promise<Response> {
  return aimChatHandler(req);
}
