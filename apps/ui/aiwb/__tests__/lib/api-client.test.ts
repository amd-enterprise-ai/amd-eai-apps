// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { describe, it, expect } from 'vitest';
import { getApiClientErrorMessage } from '@/lib/api-client';

describe('getApiClientErrorMessage', () => {
  // openapi-fetch has already drained the body, so the response body is
  // unusable — these assertions confirm the message is read from the drained
  // `error` value rather than re-reading the response.
  const drainedResponse = () =>
    new Response('drained', { status: 400, statusText: 'Bad Request' });

  it('returns a raw string error verbatim', () => {
    expect(getApiClientErrorMessage('boom', drainedResponse())).toBe('boom');
  });

  it('extracts the error field from a parsed body', () => {
    expect(
      getApiClientErrorMessage(
        { error: 'from error field' },
        drainedResponse(),
      ),
    ).toBe('from error field');
  });

  it('extracts the message field when error is absent', () => {
    expect(
      getApiClientErrorMessage({ message: 'from message' }, drainedResponse()),
    ).toBe('from message');
  });

  it('extracts the FastAPI detail field when other fields are absent', () => {
    expect(
      getApiClientErrorMessage({ detail: 'from detail' }, drainedResponse()),
    ).toBe('from detail');
  });

  it('unwraps a nested APIErrorContent message', () => {
    expect(
      getApiClientErrorMessage(
        { error: { message: 'nested detail' } },
        drainedResponse(),
      ),
    ).toBe('nested detail');
  });

  it('falls back to statusText when the nested message is not a usable string', () => {
    expect(
      getApiClientErrorMessage({ error: { message: null } }, drainedResponse()),
    ).toBe('Bad Request');
  });

  it('falls back to statusText when the error carries no message', () => {
    expect(getApiClientErrorMessage({}, drainedResponse())).toBe('Bad Request');
  });

  it('falls back to a default when statusText is empty', () => {
    const response = new Response('', { status: 500, statusText: '' });
    expect(getApiClientErrorMessage(undefined, response)).toBe(
      'An unknown error occurred',
    );
  });
});
