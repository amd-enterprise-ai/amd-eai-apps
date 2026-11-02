// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  buildOnboardSourceFields,
  buildPreviewRequest,
  getModelOnboardingStatus,
  isValidS3Uri,
  onboardModel,
  previewModelSource,
} from '@/lib/app/model-import';

import { APIRequestError } from '@amdenterpriseai/utils/app';

import type { components } from '@/types/api';

// Typed-apiClient mock: preview and onboard ride the generated POST contract, so
// the tests mock the client (not globalThis.fetch) and assert the typed
// path/param envelope. getModelOnboardingStatus still uses raw fetch (its
// `/onboarding` path is not in the OpenAPI schema), so a fetch mock is kept for
// that one function only.
const mockPOST = vi.fn();

vi.mock('@/lib/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api-client')>();
  return {
    ...actual,
    apiClient: {
      POST: (...args: unknown[]) => mockPOST(...args),
    },
  };
});

vi.mock('@amdenterpriseai/utils/app', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@amdenterpriseai/utils/app')>();
  return {
    ...actual,
    getErrorMessage: vi.fn().mockResolvedValue('upstream'),
  };
});

const mockFetch = vi.fn();
global.fetch = mockFetch;

type PreviewResponse = components['schemas']['PreviewResponse'];
type OnboardRequest = components['schemas']['OnboardRequest'];

const onboardBody: OnboardRequest = {
  sourceType: 'huggingFace',
  repoId: 'meta-llama/Llama-3',
  revision: 'main',
  sha: 'abc123',
  displayName: 'My Model',
  description: 'A model',
  tags: ['llama'],
  image: 'amdenterpriseai/aim-base:0.11',
  hfTokenSecretName: 'hf-secret-1',
  customProfile: {
    imageFamilyId: 'aim-base',
    image: 'amdenterpriseai/aim-base:0.11',
    acceleratorType: 'gpu',
    acceleratorModel: '74a1',
    acceleratorCount: 1,
    precision: 'bf16',
  },
};

const previewResponse: PreviewResponse = {
  sourceType: 'huggingFace',
  repoId: 'a/b',
  revision: 'main',
  sha: 'sha-1',
  displayName: 'X',
  description: '',
  tags: [],
  gated: false,
  hfTokenRecommended: false,
  weightFiles: [],
};

const okData = <T>(data: T) => ({
  data,
  error: undefined,
  response: { status: 200 } as Response,
});

const apiError = (status: number) => ({
  data: undefined,
  error: { detail: 'boom' },
  response: { status } as Response,
});

const rawOkResponse = <T>(body: T) => ({
  ok: true,
  json: () => Promise.resolve(body),
});

const rawErrorResponse = (status: number) => ({
  ok: false,
  status,
  text: () => Promise.resolve('upstream'),
});

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('model-import', () => {
  describe('isValidS3Uri', () => {
    it.each([
      's3://bucket/models/llama',
      's3://bucket/one-level',
      '  s3://bucket/models/llama/  ',
    ])('accepts %s', (source) => {
      expect(isValidS3Uri(source)).toBe(true);
    });

    it.each([
      's3://bucket',
      's3://bucket/',
      's3://bucket///',
      'https://bucket/models',
      'meta-llama/Llama-3',
      '',
    ])('rejects %s', (source) => {
      expect(isValidS3Uri(source)).toBe(false);
    });
  });

  describe('buildOnboardSourceFields', () => {
    it('sends only the S3 credential for an S3 source', () => {
      expect(
        buildOnboardSourceFields({
          sourceType: 's3',
          source: 's3://bucket/models',
          hfTokenSecretName: 'hf-token',
          s3StorageName: ' s3-creds ',
        }),
      ).toEqual({ sourceType: 's3', s3StorageName: 's3-creds' });
    });

    it('omits the S3 credential entirely when none is selected', () => {
      const fields = buildOnboardSourceFields({
        sourceType: 's3',
        source: 's3://bucket/models',
        s3StorageName: '   ',
      });
      expect(fields).toEqual({ sourceType: 's3' });
      expect(fields).not.toHaveProperty('s3StorageName');
    });

    it('omits the Hugging Face token entirely when none is selected', () => {
      const fields = buildOnboardSourceFields({
        sourceType: 'huggingFace',
        source: 'meta-llama/Llama-3',
        hfTokenSecretName: '   ',
        s3StorageName: 's3-creds',
      });
      expect(fields).toEqual({ sourceType: 'huggingFace' });
      expect(fields).not.toHaveProperty('s3StorageName');
    });
  });

  describe('buildPreviewRequest', () => {
    it('trims the source alongside the source-specific credential', () => {
      expect(
        buildPreviewRequest({
          sourceType: 'huggingFace',
          source: '  meta-llama/Llama-3  ',
          hfTokenSecretName: 'hf-token',
        }),
      ).toEqual({
        sourceType: 'huggingFace',
        source: 'meta-llama/Llama-3',
        hfTokenSecretName: 'hf-token',
      });
    });
  });

  describe('previewModelSource', () => {
    it('rejects an empty project name without touching the client', async () => {
      await expect(
        previewModelSource('', {
          sourceType: 'huggingFace',
          source: 'hf/model',
        }),
      ).rejects.toBeInstanceOf(APIRequestError);
      expect(mockPOST).not.toHaveBeenCalled();
    });

    it('rejects a blank model source without touching the client', async () => {
      await expect(
        previewModelSource('ns-1', {
          sourceType: 'huggingFace',
          source: '   ',
        }),
      ).rejects.toMatchObject({ statusCode: 422 });
      expect(mockPOST).not.toHaveBeenCalled();
    });

    it('POSTs to the typed preview path with the full body', async () => {
      mockPOST.mockResolvedValue(okData(previewResponse));
      const body = {
        sourceType: 'huggingFace' as const,
        source: 'a/b',
        hfTokenSecretName: 'project-hf-token',
      };

      const result = await previewModelSource('my-project', body);

      expect(mockPOST).toHaveBeenCalledWith(
        '/api/projects/{project}/models/preview',
        { params: { path: { project: 'my-project' } }, body },
      );
      expect(result).toEqual(previewResponse);
    });

    it('returns the typed data uncast', async () => {
      const inner: PreviewResponse = {
        ...previewResponse,
        repoId: 'x/y',
        gated: true,
        hfTokenRecommended: true,
        weightFiles: [{ path: 'w.bin', sizeBytes: 1, role: 'primary' }],
      };
      mockPOST.mockResolvedValue(okData(inner));
      const result = await previewModelSource('ns', {
        sourceType: 'huggingFace',
        source: 'x/y',
      });
      expect(result).toEqual(inner);
    });

    it('throws APIRequestError carrying the upstream status when the client returns an error', async () => {
      mockPOST.mockResolvedValue(apiError(502));
      await expect(
        previewModelSource('ns', { sourceType: 'huggingFace', source: 'x/y' }),
      ).rejects.toMatchObject({ statusCode: 502 });
    });

    it('rejects an S3 source with no credential without touching the client', async () => {
      await expect(
        previewModelSource('ns', {
          sourceType: 's3',
          source: 's3://bucket/models',
        }),
      ).rejects.toMatchObject({ statusCode: 422 });
      expect(mockPOST).not.toHaveBeenCalled();
    });
  });

  describe('onboardModel', () => {
    it('rejects an empty project name', async () => {
      await expect(onboardModel('', onboardBody)).rejects.toMatchObject({
        statusCode: 422,
      });
      expect(mockPOST).not.toHaveBeenCalled();
    });

    it('requires the preview hub identifiers', async () => {
      await expect(
        onboardModel('ns', { ...onboardBody, sha: '' }),
      ).rejects.toMatchObject({ statusCode: 422 });
      expect(mockPOST).not.toHaveBeenCalled();
    });

    it('requires a container image ref', async () => {
      await expect(
        onboardModel('ns', { ...onboardBody, image: '' }),
      ).rejects.toMatchObject({ statusCode: 422 });
      expect(mockPOST).not.toHaveBeenCalled();
    });

    it('POSTs to the typed onboard path with the full body', async () => {
      mockPOST.mockResolvedValue({
        data: undefined,
        error: undefined,
        response: { status: 204, ok: true } as Response,
      });

      await onboardModel('my-project', onboardBody);

      expect(mockPOST).toHaveBeenCalledWith(
        '/api/projects/{project}/models/onboard',
        { params: { path: { project: 'my-project' } }, body: onboardBody },
      );
    });

    it('resolves to void on a 204 No Content response', async () => {
      mockPOST.mockResolvedValue({
        data: undefined,
        error: undefined,
        response: { status: 204, ok: true } as Response,
      });
      await expect(onboardModel('ns', onboardBody)).resolves.toBeUndefined();
    });

    it('throws APIRequestError carrying the upstream status on error', async () => {
      mockPOST.mockResolvedValue(apiError(500));
      await expect(onboardModel('ns', onboardBody)).rejects.toMatchObject({
        statusCode: 500,
      });
    });

    it('rejects an S3 onboard with no credential', async () => {
      await expect(
        onboardModel('ns', {
          ...onboardBody,
          sourceType: 's3',
          hfTokenSecretName: undefined,
          repoId: 's3://bucket/models',
        }),
      ).rejects.toMatchObject({ statusCode: 422 });
      expect(mockPOST).not.toHaveBeenCalled();
    });
  });

  describe('getModelOnboardingStatus', () => {
    it('rejects an empty project name', async () => {
      await expect(getModelOnboardingStatus('', 'id-1')).rejects.toMatchObject({
        statusCode: 422,
      });
      expect(mockFetch).not.toHaveBeenCalled();
    });

    it('rejects an empty model id', async () => {
      await expect(getModelOnboardingStatus('ns', '')).rejects.toMatchObject({
        statusCode: 422,
      });
      expect(mockFetch).not.toHaveBeenCalled();
    });

    it('GETs the onboarding-status route with encoded params', async () => {
      mockFetch.mockResolvedValueOnce(
        rawOkResponse({ onboardingStatus: 'ready', percentComplete: 100 }),
      );

      await getModelOnboardingStatus('my project', 'mod/abc');

      expect(mockFetch).toHaveBeenCalledTimes(1);
      const [url, init] = mockFetch.mock.calls[0] as [string, RequestInit?];
      expect(url).toBe(
        '/api/projects/my%20project/models/mod%2Fabc/onboarding',
      );
      expect(init).toBeUndefined();
    });

    it('throws APIRequestError when the response is not ok', async () => {
      mockFetch.mockResolvedValueOnce(rawErrorResponse(404));
      await expect(
        getModelOnboardingStatus('ns', 'missing'),
      ).rejects.toMatchObject({ statusCode: 404 });
    });
  });
});
