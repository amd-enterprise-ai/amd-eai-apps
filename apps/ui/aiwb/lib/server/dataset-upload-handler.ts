// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { NextRequest, NextResponse } from 'next/server';

import { authenticateRoute, handleError } from '@amdenterpriseai/utils/server';

import type { components } from '@/types/api';

import { extractApiPath } from './route-utils';
import { validatePathSegments } from './proxy-handler';

type DatasetResponse = components['schemas']['DatasetResponse'];

export const maxDuration = 3600;

async function datasetUploadHandler(req: NextRequest): Promise<Response> {
  try {
    const apiPath = extractApiPath(req);
    const segments = apiPath.split('/').filter(Boolean);
    validatePathSegments(segments);

    const { accessToken } = await authenticateRoute();
    const url = `${process.env.AIRM_API_SERVICE_URL}/v1/${apiPath}`;

    const response = await fetch(url, {
      headers: {
        Authorization: `Bearer ${accessToken}`,
        'Content-Type': req.headers.get('content-type') || '',
      },
      method: 'POST',
      // @ts-expect-error - duplex is not yet in TypeScript types but is required for streaming
      duplex: 'half',
      body: req.body,
    });

    if (!response.ok) {
      const errorData = await response.json();
      return NextResponse.json(errorData, { status: response.status });
    }

    const data = (await response.json()) as DatasetResponse;
    return NextResponse.json(data);
  } catch (error) {
    return handleError(error);
  }
}

export function POST(req: NextRequest): Promise<Response> {
  return datasetUploadHandler(req);
}
