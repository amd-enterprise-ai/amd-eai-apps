// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

/**
 * BFF route for reading, updating and deleting one custom profile of a model.
 *
 * Browser-facing path:  GET|PATCH|DELETE /api/projects/{project}/models/{modelId}/profiles/{profileId}
 * Upstream AIWB API:    GET|PATCH|DELETE /v1/projects/{project}/models/{model}/profiles/{profile}
 *
 * `{profileId}` is the AIMProfileSet resource name, or the reserved literal
 * `default` for the onboarding profile. DELETE returns 204, 409 when a
 * deployment still references the profile, or 422 for `default` (which has no
 * stored record to delete). PATCH carries merge-patch semantics and returns 409
 * both when a deployment references the profile and when the requested display
 * name is taken, or 422 for `default` (edited through model settings instead).
 *
 * Handlers are thin wrappers (not `export { … } from`) so Next always registers
 * every verb for this route in dev and production builds.
 */

import type { NextRequest } from 'next/server';

import {
  DELETE as proxyDelete,
  GET as proxyGet,
  PATCH as proxyPatch,
} from '@/lib/server/proxy-handler';

export function GET(request: NextRequest) {
  return proxyGet(request);
}

export function PATCH(request: NextRequest) {
  return proxyPatch(request);
}

export function DELETE(request: NextRequest) {
  return proxyDelete(request);
}
