// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { afterEach, beforeEach, describe, expect, it, Mock, vi } from 'vitest';

import {
  cancelFineTuningJob,
  deleteModel,
  finetuneModel,
} from '@/lib/app/models';
import { apiClient } from '@/lib/api-client';

import { APIRequestError } from '@amdenterpriseai/utils/app';

// deleteModel, finetuneModel and cancelFineTuningJob go through the typed
// apiClient (openapi-fetch), which builds a Request from a browser-relative URL
// — jsdom's Request rejects that, so a raw global-fetch mock can't intercept
// them. Mock the apiClient methods directly and assert on the typed call
// arguments (path key + params/body) instead of a raw fetch URL string.
vi.mock('@/lib/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api-client')>();
  return {
    ...actual,
    apiClient: { GET: vi.fn(), POST: vi.fn(), PATCH: vi.fn(), DELETE: vi.fn() },
  };
});

const mockPost = apiClient.POST as Mock;
const mockDelete = apiClient.DELETE as Mock;

const errResponse = (status: number) => ({
  status,
  json: () => Promise.resolve({ detail: 'boom' }),
  text: () => Promise.resolve('boom'),
});

describe('Models Service', () => {
  const mockProjectId = 'test-project-id';
  const mockModelId = 'test-model-id';

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    mockPost.mockReset();
    mockDelete.mockReset();
  });

  describe('deleteModel', () => {
    it('DELETEs the typed fine-tuning model path with path params', async () => {
      mockDelete.mockResolvedValueOnce({ data: undefined, error: undefined });

      const result = await deleteModel(mockModelId, mockProjectId);

      expect(mockDelete).toHaveBeenCalledWith(
        '/api/projects/{project}/fine-tuning/models/{model_id}',
        {
          params: { path: { project: mockProjectId, model_id: mockModelId } },
        },
      );
      // 204 No Content — deleteModel returns void
      expect(result).toBeUndefined();
    });

    it('adds the force query param when force is true', async () => {
      mockDelete.mockResolvedValueOnce({ data: undefined, error: undefined });

      await deleteModel(mockModelId, mockProjectId, true);

      expect(mockDelete).toHaveBeenCalledWith(
        '/api/projects/{project}/fine-tuning/models/{model_id}',
        {
          params: {
            path: { project: mockProjectId, model_id: mockModelId },
            query: { force: true },
          },
        },
      );
    });

    it('throws APIRequestError when the typed client returns an error', async () => {
      mockDelete.mockResolvedValueOnce({
        data: undefined,
        error: { detail: 'boom' },
        response: errResponse(404),
      });

      const error = await deleteModel(mockModelId, mockProjectId).catch(
        (e) => e,
      );
      expect(error).toBeInstanceOf(APIRequestError);
      expect(error.statusCode).toBe(404);
      expect((error as APIRequestError).message).toContain(
        'Failed to delete model',
      );
    });

    it('propagates network rejections from the typed client', async () => {
      mockDelete.mockRejectedValueOnce(new Error('Network error'));

      await expect(deleteModel(mockModelId, mockProjectId)).rejects.toThrow(
        'Network error',
      );
    });
  });

  describe('finetuneModel', () => {
    it('POSTs the typed fine-tuning jobs path without hfTokenSecretName', async () => {
      const mockParams = {
        displayName: 'test-finetuned-model',
        datasetIds: ['dataset-123'],
        epochs: 10,
        learningRate: 0.001,
        batchSize: 8,
      };
      const mockResponse = {
        id: 'model-123',
        displayName: 'test-finetuned-model',
      };
      mockPost.mockResolvedValueOnce({ data: mockResponse, error: undefined });

      const result = await finetuneModel(
        mockModelId,
        mockParams,
        mockProjectId,
      );

      expect(mockPost).toHaveBeenCalledWith(
        '/api/projects/{project}/fine-tuning/jobs',
        {
          params: { path: { project: mockProjectId } },
          body: {
            baseModel: mockModelId,
            displayName: mockParams.displayName,
            datasetIds: mockParams.datasetIds,
            epochs: mockParams.epochs,
            learningRate: mockParams.learningRate,
            batchSize: mockParams.batchSize,
          },
        },
      );
      expect(result).toEqual(mockResponse);
    });

    it('includes hfTokenSecretName in the body when provided', async () => {
      const mockParams = {
        displayName: 'test-finetuned-model',
        datasetIds: ['dataset-123'],
        epochs: 10,
        learningRate: 0.001,
        batchSize: 8,
        hfTokenSecretName: 'hf-token-secret',
      };
      mockPost.mockResolvedValueOnce({ data: {}, error: undefined });

      await finetuneModel(mockModelId, mockParams, mockProjectId);

      expect(mockPost).toHaveBeenCalledWith(
        '/api/projects/{project}/fine-tuning/jobs',
        {
          params: { path: { project: mockProjectId } },
          body: {
            baseModel: mockModelId,
            displayName: mockParams.displayName,
            datasetIds: mockParams.datasetIds,
            epochs: mockParams.epochs,
            learningRate: mockParams.learningRate,
            batchSize: mockParams.batchSize,
            hfTokenSecretName: mockParams.hfTokenSecretName,
          },
        },
      );
    });

    it('omits hfTokenSecretName from the body when not provided', async () => {
      const mockParams = {
        displayName: 'test-finetuned-model',
        datasetIds: ['dataset-123'],
        epochs: 10,
        learningRate: 0.001,
        batchSize: 8,
      };
      mockPost.mockResolvedValueOnce({ data: {}, error: undefined });

      await finetuneModel(mockModelId, mockParams, mockProjectId);

      const body = mockPost.mock.calls[0][1].body as Record<string, unknown>;
      expect(body).not.toHaveProperty('hfTokenSecretName');
    });

    it('omits missing hyperparameters so the server applies its own defaults', async () => {
      const mockParams = {
        displayName: 'test-finetuned-model',
        datasetIds: ['dataset-123'],
      };
      mockPost.mockResolvedValueOnce({ data: {}, error: undefined });

      await finetuneModel(mockModelId, mockParams, mockProjectId);

      const body = mockPost.mock.calls[0][1].body as Record<string, unknown>;
      expect(body).not.toHaveProperty('epochs');
      expect(body).not.toHaveProperty('learningRate');
      expect(body).not.toHaveProperty('batchSize');
    });

    it('includes description in the body when provided', async () => {
      const mockParams = {
        displayName: 'test-finetuned-model',
        datasetIds: ['dataset-123'],
        description: 'A helpful description',
      };
      mockPost.mockResolvedValueOnce({ data: {}, error: undefined });

      await finetuneModel(mockModelId, mockParams, mockProjectId);

      const body = mockPost.mock.calls[0][1].body as Record<string, unknown>;
      expect(body).toHaveProperty('description', 'A helpful description');
    });

    it('omits description from the body when not provided', async () => {
      const mockParams = {
        displayName: 'test-finetuned-model',
        datasetIds: ['dataset-123'],
      };
      mockPost.mockResolvedValueOnce({ data: {}, error: undefined });

      await finetuneModel(mockModelId, mockParams, mockProjectId);

      const body = mockPost.mock.calls[0][1].body as Record<string, unknown>;
      expect(body).not.toHaveProperty('description');
    });

    it('includes adapter output and LoRA settings when provided', async () => {
      const mockParams = {
        displayName: 'test-lora',
        datasetIds: ['dataset-123'],
        output: 'adapter' as const,
        lora: { rank: 16, alpha: 32, dropout: 0.05 },
      };
      mockPost.mockResolvedValueOnce({ data: {}, error: undefined });

      await finetuneModel(mockModelId, mockParams, mockProjectId);

      expect(mockPost.mock.calls[0][1].body).toMatchObject({
        output: 'adapter',
        lora: mockParams.lora,
      });
    });

    it('omits a non-finite hyperparameter (e.g. NaN from an untouched field) rather than sending it', async () => {
      const mockParams = {
        displayName: 'test-finetuned-model',
        datasetIds: ['dataset-123'],
        epochs: Number.NaN,
        learningRate: 10,
      };
      mockPost.mockResolvedValueOnce({ data: {}, error: undefined });

      await finetuneModel(mockModelId, mockParams, mockProjectId);

      const body = mockPost.mock.calls[0][1].body as Record<string, unknown>;
      expect(body).not.toHaveProperty('epochs');
      expect(body).toHaveProperty('learningRate', 10);
    });

    it('throws APIRequestError when the typed client returns an error', async () => {
      const mockParams = {
        displayName: 'test-finetuned-model',
        datasetIds: ['dataset-123'],
        epochs: 10,
        learningRate: 0.001,
        batchSize: 8,
      };
      mockPost.mockResolvedValueOnce({
        data: undefined,
        error: { detail: 'boom' },
        response: errResponse(400),
      });

      const error = await finetuneModel(
        mockModelId,
        mockParams,
        mockProjectId,
      ).catch((e) => e);

      expect(error).toBeInstanceOf(APIRequestError);
      expect((error as APIRequestError).message).toContain(
        'Failed to finetune model',
      );
    });
  });

  describe('cancelFineTuningJob', () => {
    const mockJobId = 'job-uuid-1';

    it('DELETEs the typed fine-tuning job path with path params', async () => {
      mockDelete.mockResolvedValueOnce({ data: undefined, error: undefined });

      const result = await cancelFineTuningJob(mockJobId, mockProjectId);

      expect(mockDelete).toHaveBeenCalledWith(
        '/api/projects/{project}/fine-tuning/jobs/{job_id}',
        {
          params: { path: { project: mockProjectId, job_id: mockJobId } },
        },
      );
      expect(result).toBeUndefined();
    });

    it('throws APIRequestError when the job is not found', async () => {
      mockDelete.mockResolvedValueOnce({
        data: undefined,
        error: { detail: 'boom' },
        response: errResponse(404),
      });

      const error = await cancelFineTuningJob(mockJobId, mockProjectId).catch(
        (e) => e,
      );

      expect(error).toBeInstanceOf(APIRequestError);
      expect(error.statusCode).toBe(404);
      expect((error as APIRequestError).message).toContain(
        'Failed to cancel fine-tuning job',
      );
    });
  });
});
