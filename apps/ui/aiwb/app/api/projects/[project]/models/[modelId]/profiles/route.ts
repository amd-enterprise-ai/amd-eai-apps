// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

/**
 * BFF route for listing and creating the custom profiles of a custom model.
 *
 * Browser-facing path:  GET|POST /api/projects/{project}/models/{modelId}/profiles
 * Upstream AIWB API:    GET|POST /v1/projects/{project}/models/{model}/profiles
 *
 * GET returns the synthetic Default entry plus every named profile, unpaginated.
 * POST creates a named profile and answers with it, 409 when a sibling profile
 * already uses the requested display name, or 422 for a reserved or empty name.
 * Upstream answers a create with 201; the shared proxy forwards the body under
 * its own 200, as it does for every other write in this app.
 *
 * Handlers are thin wrappers (not `export { … } from`) so Next always registers
 * every verb for this route in dev and production builds.
 */

import type { NextRequest } from 'next/server';

import { GET as proxyGet, POST as proxyPost } from '@/lib/server/proxy-handler';

export function GET(request: NextRequest) {
  return proxyGet(request);
}

export function POST(request: NextRequest) {
  return proxyPost(request);
}
