// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

/**
 * Type-safe API client (openapi-fetch). Paths and response/error types are
 * inferred from the generated OpenAPI schema. Call the Next.js proxy paths
 * (/api/...), which this client maps from the backend /v1/... path keys.
 *
 * Usage:
 *   const { data, error } = await apiClient.GET('/api/charts');
 *   const { data } = await apiClient.POST('/api/charts', { body: chartData });
 */
import createClient from 'openapi-fetch';
import type { paths } from '@/types/api';

// Maps every backend /v1 path to its Next.js proxy /api path; non-/v1 backend
// keys are dropped (never). The mapping is optimistic: each proxy is a
// hand-written route, so a /v1 path with no corresponding /api route still
// type-checks here but 404s at runtime.
type ApiPaths = {
  [K in keyof paths as K extends `/v1${infer R}`
    ? `/api${R}`
    : never]: paths[K];
};

// baseUrl '' yields browser-relative /api/... URLs, so this client is for
// client-side use. Server-side callers (Node fetch rejects relative URLs) must
// supply an absolute base.
export const apiClient = createClient<ApiPaths>({ baseUrl: '' });

/**
 * Extracts a human-readable message from an {@link apiClient} error result.
 *
 * openapi-fetch drains the response body into the `error` value (parsed JSON
 * when the body is JSON, otherwise the raw string) before returning, so the
 * response body is already consumed. Read the drained `error` instead, applying
 * `error` / `message` / `detail` field precedence, and fall back to the
 * response status text when the error carries no usable message.
 */
export const getApiClientErrorMessage = (
  error: unknown,
  response: Response,
): string => {
  if (typeof error === 'string' && error.length > 0) {
    return error;
  }
  if (error && typeof error === 'object') {
    const body = error as Record<string, unknown>;
    const errorValue = body.error ?? body.message ?? body.detail;
    if (
      errorValue &&
      typeof errorValue === 'object' &&
      'message' in errorValue
    ) {
      const nested = (errorValue as { message: unknown }).message;
      if (typeof nested === 'string' && nested.length > 0) {
        return nested;
      }
    }
    if (typeof errorValue === 'string' && errorValue.length > 0) {
      return errorValue;
    }
  }
  return response.statusText || 'An unknown error occurred';
};
