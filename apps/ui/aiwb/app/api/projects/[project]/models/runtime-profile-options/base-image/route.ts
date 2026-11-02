// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

/**
 * BFF proxy: GET /api/projects/{project}/models/runtime-profile-options/base-image
 * → /v1/.../runtime-profile-options/base-image.
 *
 * Explicit sub-route so image-scoped runtime-options requests are forwarded
 * instead of falling through to Next's 404.
 */

import type { NextRequest } from 'next/server';

import { GET as proxyGet } from '@/lib/server/proxy-handler';

export function GET(request: NextRequest) {
  return proxyGet(request);
}
