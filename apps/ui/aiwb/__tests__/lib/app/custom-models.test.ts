// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { beforeEach, describe, expect, it, vi } from 'vitest';

import { APIRequestError } from '@amdenterpriseai/utils/app';

import {
  collectExistingDisplayNames,
  copyCustomModel,
  customModelToAggregatedAIM,
  deleteCustomModel,
  extractCustomModelCanonicalName,
  extractCustomModelDisplayMetadata,
  extractCustomModelPrecision,
  getCustomModel,
  getRuntimeProfileOptions,
  listCustomModels,
  normalizeCustomModelDisplayName,
  parseCustomModelDeleteErrorBody,
  patchCustomModel,
} from '@/lib/app/custom-models';
import type { components } from '@/types/api';

type CustomModelResponse = components['schemas']['CustomModelResponse'];

// Reusable typed-apiClient mock. Each verb is a vi.fn() the service layer awaits
// for an openapi-fetch `{ data, error, response }` envelope; tests set the
// resolved value per case. Mock the client (not globalThis.fetch) so assertions
// ride the typed path/param contract instead of URL strings.
const mockGET = vi.fn();
const mockPOST = vi.fn();
const mockDELETE = vi.fn();
const mockPATCH = vi.fn();

vi.mock('@/lib/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api-client')>();
  return {
    ...actual,
    apiClient: {
      GET: (...args: unknown[]) => mockGET(...args),
      POST: (...args: unknown[]) => mockPOST(...args),
      DELETE: (...args: unknown[]) => mockDELETE(...args),
      PATCH: (...args: unknown[]) => mockPATCH(...args),
    },
  };
});

vi.mock('@amdenterpriseai/utils/app', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@amdenterpriseai/utils/app')>();
  return {
    ...actual,
    getErrorMessage: vi.fn().mockResolvedValue('error message'),
  };
});

const emptyMetadata = {
  name: 'cr-name',
  namespace: 'workbench',
  labels: {},
  annotations: {},
  creationTimestamp: '2026-06-08T21:00:00Z',
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const ANNOTATIONS = {
  'aiwb.apps.eai.amd.com/model-display-name': 'Gemma 3 1B IT',
  'aiwb.apps.eai.amd.com/canonical-repo-id': 'google/gemma-3-1b-it',
  'aiwb.apps.eai.amd.com/source-description': 'Google Gemma 3 1B model',
  'aiwb.apps.eai.amd.com/source-tags': '["text-generation","pytorch"]',
  'airm.silogen.ai/revision': 'dcc83ea841ab6100d6b47a070329e1ba4cf78752',
};

function buildCustomModel(
  overrides: Partial<CustomModelResponse> = {},
): CustomModelResponse {
  return {
    metadata: {
      name: 'gemma3-1b-it-custom-import-d41ec23c',
      namespace: 'workbench',
      labels: { 'aiwb.apps.eai.amd.com/model-source-type': 'custom' },
      annotations: ANNOTATIONS,
      creationTimestamp: '2026-06-08T21:00:00Z',
    },
    spec: {
      aimId: 'google/gemma-3-1b-it',
      // top-level image is empty for v1alpha2; image lives under profiles.overrides.image
      image: '',
      modelSources: [],
      profiles: {
        overrides: {
          image: 'docker.io/amd/gemma3-1b-it:1.0.0',
          modelSources: [
            {
              modelId: 'google/gemma-3-1b-it',
              sourceUri:
                's3://workbench-bucket/gemma3-1b-it-custom-import-d41ec23c/weights',
            },
          ],
        },
      },
    },
    phase: {
      state: 'Ready',
      status: 'Ready',
      templateReady: true,
      artifactPhase: null,
      artifactLastError: null,
    },
    profiles: [],
    ...overrides,
  };
}

type CustomProfileResponse = components['schemas']['CustomProfileResponse'];

function buildProfile(
  overrides: Partial<CustomProfileResponse> = {},
): CustomProfileResponse {
  return {
    name: 'default',
    displayName: 'Default',
    isDefault: true,
    resourceName: 'gemma3-1b-it-custom-import-d41ec23c-default',
    ...overrides,
  };
}

const okData = (data: unknown) => ({
  data,
  error: undefined,
  response: { status: 200 } as Response,
});

beforeEach(() => {
  vi.clearAllMocks();
});

// ---------------------------------------------------------------------------
// customModelToAggregatedAIM
// ---------------------------------------------------------------------------

describe('customModelToAggregatedAIM', () => {
  it('sets isSupported and latestAim when phase.state is Ready', () => {
    const result = customModelToAggregatedAIM(buildCustomModel());

    expect(result.isSupported).toBe(true);
    expect(result.latestAim).not.toBeNull();
  });

  it('clears isSupported and latestAim when phase.state is not Ready', () => {
    const model = buildCustomModel({
      phase: {
        state: 'Pending',
        status: 'Pending',
        templateReady: false,
        artifactPhase: null,
        artifactLastError: null,
      },
    });

    const result = customModelToAggregatedAIM(model);

    expect(result.isSupported).toBe(false);
    expect(result.latestAim).toBeNull();
  });

  it('clears isSupported and latestAim when the weight import failed even though templateReady is true', () => {
    // The bug: an AIMProfile (templateReady) derives from the base image, so it
    // can be present while the weight import failed. Deployability must gate on
    // the composed state, not templateReady, or the predictor crashloops with
    // missing weights.
    const model = buildCustomModel({
      phase: {
        state: 'Failed',
        status: 'Ready',
        templateReady: true,
        artifactPhase: 'Failed',
        artifactLastError: 'MinIO returned HTTP 500 (disk full)',
      },
    });

    const result = customModelToAggregatedAIM(model);

    expect(result.isSupported).toBe(false);
    expect(result.latestAim).toBeNull();
    expect(result.aggregated.onboardPhase).toBe('Failed');
  });

  it('extracts display name from annotation', () => {
    const result = customModelToAggregatedAIM(buildCustomModel());

    expect(result.aggregated.title).toBe('Gemma 3 1B IT');
    expect(result.parsedAIMs[0].title).toBe('Gemma 3 1B IT');
  });

  it('falls back to metadata.name when display-name annotation is absent', () => {
    const model = buildCustomModel({
      metadata: {
        name: 'my-model-cr-name',
        namespace: 'workbench',
        labels: {},
        annotations: {},
        creationTimestamp: '2026-06-08T21:00:00Z',
      },
    });

    const result = customModelToAggregatedAIM(model);

    expect(result.aggregated.title).toBe('my-model-cr-name');
  });

  it('extracts canonical name and derives aiLabName from org prefix', () => {
    const result = customModelToAggregatedAIM(buildCustomModel());

    expect(result.aggregated.canonicalName).toBe('google/gemma-3-1b-it');
    expect(result.aggregated.aiLabName).toBe('google');
  });

  it('parses tags from annotation JSON', () => {
    const result = customModelToAggregatedAIM(buildCustomModel());

    expect(result.aggregated.tags).toEqual(['text-generation', 'pytorch']);
  });

  it('returns empty tags when annotation is absent', () => {
    const model = buildCustomModel({
      metadata: {
        name: 'test-model',
        namespace: 'workbench',
        labels: {},
        annotations: {},
        creationTimestamp: '2026-06-08T21:00:00Z',
      },
    });

    const result = customModelToAggregatedAIM(model);

    expect(result.aggregated.tags).toEqual([]);
  });

  it('derives image from spec.profiles.overrides.image', () => {
    const result = customModelToAggregatedAIM(buildCustomModel());

    expect(result.parsedAIMs[0].imageReference).toBe(
      'docker.io/amd/gemma3-1b-it:1.0.0',
    );
  });

  it('falls back to spec.image when profiles.overrides.image is absent', () => {
    const model = buildCustomModel({
      spec: {
        aimId: null,
        image: 'fallback-image:latest',
        modelSources: [],
        profiles: { overrides: {} },
      },
    });

    expect(customModelToAggregatedAIM(model).parsedAIMs[0].imageReference).toBe(
      'fallback-image:latest',
    );
  });

  it('derives sourceUri from spec.profiles.overrides.modelSources[0]', () => {
    const result = customModelToAggregatedAIM(buildCustomModel());

    expect(result.parsedAIMs[0].sourceUri).toBe(
      's3://workbench-bucket/gemma3-1b-it-custom-import-d41ec23c/weights',
    );
  });

  it('derives revision from the revision annotation', () => {
    const result = customModelToAggregatedAIM(buildCustomModel());

    const sha = 'dcc83ea841ab6100d6b47a070329e1ba4cf78752';
    expect(result.parsedAIMs[0].imageVersion).toBe(sha);
    expect(result.aggregated.latestImageVersion).toBe(sha);
  });

  it('sets isHfTokenRequired when HF_TOKEN env entry is present in model source', () => {
    const model = buildCustomModel({
      spec: {
        aimId: null,
        image: '',
        modelSources: [],
        profiles: {
          overrides: {
            modelSources: [
              {
                modelId: 'org/model',
                sourceUri: 's3://bucket/weights',
                env: [{ name: 'HF_TOKEN' }],
              },
            ],
          },
        },
      },
    });

    const result = customModelToAggregatedAIM(model);

    expect(result.aggregated.isHfTokenRequired).toBe(true);
    expect(result.parsedAIMs[0].isHfTokenRequired).toBe(true);
  });

  it('clears isHfTokenRequired when no HF_TOKEN env entry is present', () => {
    const result = customModelToAggregatedAIM(buildCustomModel());

    expect(result.aggregated.isHfTokenRequired).toBe(false);
    expect(result.parsedAIMs[0].isHfTokenRequired).toBe(false);
  });

  it('passes raw controller status through to parsedAIM', () => {
    const model = buildCustomModel({
      phase: {
        state: 'Importing',
        status: 'Progressing',
        templateReady: false,
        artifactPhase: 'Progressing',
        artifactLastError: null,
      },
    });

    const result = customModelToAggregatedAIM(model);

    expect(result.parsedAIMs[0].status).toBe('Progressing');
  });

  it('propagates phase.state to aggregated.onboardPhase', () => {
    const importing = buildCustomModel({
      phase: {
        state: 'Importing',
        status: 'Progressing',
        templateReady: false,
        artifactPhase: 'Progressing',
        artifactLastError: null,
      },
    });

    const result = customModelToAggregatedAIM(importing);

    expect(result.aggregated.onboardPhase).toBe('Importing');
  });

  it('marks every model as isCustomImport', () => {
    const result = customModelToAggregatedAIM(buildCustomModel());

    expect(result.parsedAIMs[0].isCustomImport).toBe(true);
    expect(result.aggregated.isCustomImport).toBe(true);
  });

  it('uses metadata.name as the stable repository key', () => {
    const result = customModelToAggregatedAIM(buildCustomModel());

    expect(result.repository).toBe('gemma3-1b-it-custom-import-d41ec23c');
  });

  it('sets profileCount from the profiles collection length', () => {
    const model = buildCustomModel({
      profiles: [
        buildProfile({
          name: 'default',
          displayName: 'Default',
          isDefault: true,
        }),
        buildProfile({ name: 'extra', displayName: 'Extra', isDefault: false }),
      ],
    });

    const result = customModelToAggregatedAIM(model);

    expect(result.aggregated.profileCount).toBe(2);
  });

  it('selects the Default profile by its isDefault flag, not by list position', () => {
    // Backend sorts Default first, but a named row listed first must not be
    // mistaken for the Default. Select by flag so ordering changes cannot leak
    // the wrong summary onto the card.
    const named = buildProfile({
      name: 'extra',
      displayName: 'Extra',
      isDefault: false,
    });
    const dflt = buildProfile({
      name: 'default',
      displayName: 'Default',
      isDefault: true,
    });
    const model = buildCustomModel({ profiles: [named, dflt] });

    const result = customModelToAggregatedAIM(model);

    expect(result.aggregated.defaultProfile?.name).toBe('default');
  });

  it('leaves defaultProfile unset when the collection is empty', () => {
    const result = customModelToAggregatedAIM(buildCustomModel());

    expect(result.aggregated.profileCount).toBe(0);
    expect(result.aggregated.defaultProfile).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// listCustomModels
// ---------------------------------------------------------------------------

describe('listCustomModels', () => {
  it('returns mapped AggregatedAIM list from API response', async () => {
    const model = buildCustomModel();
    mockGET.mockResolvedValue(okData({ data: [model] }));

    const result = await listCustomModels('workbench');

    expect(result).toHaveLength(1);
    expect(result[0].repository).toBe('gemma3-1b-it-custom-import-d41ec23c');
    expect(mockGET).toHaveBeenCalledWith('/api/projects/{project}/models', {
      params: { path: { project: 'workbench' } },
    });
  });

  it('returns empty array when data is empty', async () => {
    mockGET.mockResolvedValue(okData({ data: [] }));

    const result = await listCustomModels('workbench');

    expect(result).toEqual([]);
  });

  it('throws without calling the client when project is empty', async () => {
    await expect(listCustomModels('')).rejects.toThrow(APIRequestError);
    expect(mockGET).not.toHaveBeenCalled();
  });

  it('throws APIRequestError when the client reports an error', async () => {
    mockGET.mockResolvedValue({
      data: undefined,
      error: { detail: 'upstream error' },
      response: { status: 502 } as Response,
    });

    await expect(listCustomModels('workbench')).rejects.toThrow(
      APIRequestError,
    );
  });
});

// ---------------------------------------------------------------------------
// getRuntimeProfileOptions
// ---------------------------------------------------------------------------

describe('getRuntimeProfileOptions', () => {
  it('returns the runtime profile options on success', async () => {
    const options = {
      acceleratorModels: ['MI300X'],
      acceleratorCounts: [1, 2],
      precisions: ['bf16'],
      optimizationClasses: ['throughput'],
    };
    mockGET.mockResolvedValue(okData(options));

    const result = await getRuntimeProfileOptions('workbench');

    expect(result).toBe(options);
    expect(mockGET).toHaveBeenCalledWith(
      '/api/projects/{project}/models/runtime-profile-options',
      { params: { path: { project: 'workbench' } } },
    );
  });

  it('throws without calling the client when project is empty', async () => {
    await expect(getRuntimeProfileOptions('')).rejects.toThrow(APIRequestError);
    expect(mockGET).not.toHaveBeenCalled();
  });

  it('throws APIRequestError when the client reports an error', async () => {
    mockGET.mockResolvedValue({
      data: undefined,
      error: { detail: 'boom' },
      response: { status: 500 } as Response,
    });

    await expect(getRuntimeProfileOptions('workbench')).rejects.toThrow(
      APIRequestError,
    );
  });
});

// ---------------------------------------------------------------------------
// extractCustomModelDisplayMetadata / extractCustomModelCanonicalName
// ---------------------------------------------------------------------------

describe('extractCustomModelDisplayMetadata', () => {
  it('reads display name, description, and tags from annotations', () => {
    expect(extractCustomModelDisplayMetadata(buildCustomModel())).toEqual({
      displayName: 'Gemma 3 1B IT',
      description: 'Google Gemma 3 1B model',
      tags: ['text-generation', 'pytorch'],
    });
  });

  it('falls back to the CR name and empty values when annotations are absent', () => {
    const model = buildCustomModel({ metadata: emptyMetadata });
    expect(extractCustomModelDisplayMetadata(model)).toEqual({
      displayName: 'cr-name',
      description: '',
      tags: [],
    });
  });
});

describe('extractCustomModelCanonicalName', () => {
  it('reads the canonical repo id annotation', () => {
    expect(extractCustomModelCanonicalName(buildCustomModel())).toBe(
      'google/gemma-3-1b-it',
    );
  });

  it('falls back to the CR name when the annotation is absent', () => {
    const model = buildCustomModel({ metadata: emptyMetadata });
    expect(extractCustomModelCanonicalName(model)).toBe('cr-name');
  });
});

describe('extractCustomModelPrecision', () => {
  it('reads the precision annotation (the CRD prunes it from overrides)', () => {
    const model = buildCustomModel({
      metadata: {
        ...emptyMetadata,
        annotations: { 'aiwb.apps.eai.amd.com/precision': 'fp8' },
      },
    });
    expect(extractCustomModelPrecision(model)).toBe('fp8');
  });

  it('returns undefined for models onboarded before precision was tracked', () => {
    const model = buildCustomModel({ metadata: emptyMetadata });
    expect(extractCustomModelPrecision(model)).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// getCustomModel
// ---------------------------------------------------------------------------

describe('getCustomModel', () => {
  it('GETs the model by project and model name', async () => {
    const model = buildCustomModel();
    mockGET.mockResolvedValue(okData(model));

    const result = await getCustomModel('workbench', 'my-model');

    expect(result.metadata.name).toBe(model.metadata.name);
    expect(mockGET).toHaveBeenCalledWith(
      '/api/projects/{project}/models/{model_name}',
      { params: { path: { project: 'workbench', model_name: 'my-model' } } },
    );
  });

  it('throws without calling the client when project or modelId is empty', async () => {
    await expect(getCustomModel('', 'my-model')).rejects.toThrow(
      APIRequestError,
    );
    await expect(getCustomModel('workbench', '')).rejects.toThrow(
      APIRequestError,
    );
    expect(mockGET).not.toHaveBeenCalled();
  });

  it('throws APIRequestError when the client reports an error', async () => {
    mockGET.mockResolvedValue({
      data: undefined,
      error: { detail: 'not found' },
      response: { status: 404 } as Response,
    });

    await expect(getCustomModel('workbench', 'my-model')).rejects.toThrow(
      APIRequestError,
    );
  });
});

// ---------------------------------------------------------------------------
// patchCustomModel
// ---------------------------------------------------------------------------

describe('patchCustomModel', () => {
  it('PATCHes the provided body to the model endpoint', async () => {
    mockPATCH.mockResolvedValue({
      error: undefined,
      response: { status: 200, ok: true } as Response,
    });

    await patchCustomModel('workbench', 'my-model', {
      displayName: 'new-name',
    });

    expect(mockPATCH).toHaveBeenCalledWith(
      '/api/projects/{project}/models/{model_name}',
      {
        params: { path: { project: 'workbench', model_name: 'my-model' } },
        body: { displayName: 'new-name' },
      },
    );
  });

  it('throws without calling the client when the body is empty', async () => {
    await expect(patchCustomModel('workbench', 'my-model', {})).rejects.toThrow(
      APIRequestError,
    );
    expect(mockPATCH).not.toHaveBeenCalled();
  });

  it('throws without calling the client when project or modelId is empty', async () => {
    await expect(
      patchCustomModel('', 'my-model', { displayName: 'x' }),
    ).rejects.toThrow(APIRequestError);
    await expect(
      patchCustomModel('workbench', '', { displayName: 'x' }),
    ).rejects.toThrow(APIRequestError);
    expect(mockPATCH).not.toHaveBeenCalled();
  });

  it('throws APIRequestError when the request fails', async () => {
    mockPATCH.mockResolvedValue({
      error: { detail: 'conflict' },
      response: { status: 409 } as Response,
    });

    await expect(
      patchCustomModel('workbench', 'my-model', { displayName: 'x' }),
    ).rejects.toThrow(APIRequestError);
  });

  it('uses a concise message for HTTP 405 (method not allowed)', async () => {
    mockPATCH.mockResolvedValue({
      error: { detail: 'Method Not Allowed' },
      response: { status: 405 } as Response,
    });

    await expect(
      patchCustomModel('workbench', 'my-model', { displayName: 'x' }),
    ).rejects.toMatchObject({
      statusCode: 405,
      message: expect.stringContaining('does not support saving these changes'),
    });
  });
});

// ---------------------------------------------------------------------------
// parseCustomModelDeleteErrorBody
// ---------------------------------------------------------------------------

describe('parseCustomModelDeleteErrorBody', () => {
  it('returns raw text as detail when the body is not JSON', () => {
    expect(parseCustomModelDeleteErrorBody('plain failure')).toEqual({
      detail: 'plain failure',
      blockingServices: [],
    });
  });

  it('uses a generic detail when JSON has no string detail', () => {
    expect(parseCustomModelDeleteErrorBody('{}')).toEqual({
      detail: 'Request failed',
      blockingServices: [],
    });
  });

  it('collects string entries from additionalInfo array', () => {
    const body = JSON.stringify({
      detail: 'Conflict',
      additionalInfo: ['svc-a', 'svc-b', 99],
    });
    expect(parseCustomModelDeleteErrorBody(body)).toEqual({
      detail: 'Conflict',
      blockingServices: ['svc-a', 'svc-b'],
    });
  });

  it('reads blockingServices from additional_info object', () => {
    const body =
      '{"detail":"In use","additional_info":{"blockingServices":["aim-svc-1"]}}';
    expect(parseCustomModelDeleteErrorBody(body)).toEqual({
      detail: 'In use',
      blockingServices: ['aim-svc-1'],
    });
  });

  it('reads displayName from object blockingServices entries', () => {
    // Profile delete sends {serviceId, displayName} objects here where model
    // delete sends bare name strings.
    const body = JSON.stringify({
      detail: 'In use',
      additionalInfo: {
        blockingServices: [
          { serviceId: 'svc-1', displayName: 'summarizer-prod' },
          { serviceId: 'svc-2' },
        ],
      },
    });
    expect(parseCustomModelDeleteErrorBody(body)).toEqual({
      detail: 'In use',
      blockingServices: ['summarizer-prod', 'svc-2'],
    });
  });

  it('accepts blockingServiceNames and services keys on additionalInfo', () => {
    expect(
      parseCustomModelDeleteErrorBody(
        JSON.stringify({
          detail: 'x',
          additionalInfo: { blockingServiceNames: ['a'] },
        }),
      ).blockingServices,
    ).toEqual(['a']);
    expect(
      parseCustomModelDeleteErrorBody(
        JSON.stringify({
          detail: 'x',
          additionalInfo: { services: ['b', 'c'] },
        }),
      ).blockingServices,
    ).toEqual(['b', 'c']);
  });

  it('uses top-level string `error` as detail when `detail` is absent', () => {
    expect(
      parseCustomModelDeleteErrorBody(
        JSON.stringify({ error: 'BFF-shaped message' }),
      ),
    ).toEqual({
      detail: 'BFF-shaped message',
      blockingServices: [],
    });
  });

  it('prefers string `detail` over string `error` when both are present', () => {
    expect(
      parseCustomModelDeleteErrorBody(
        JSON.stringify({ detail: 'canonical', error: 'other' }),
      ).detail,
    ).toBe('canonical');
  });

  it('falls back to string `error` when `detail` is not a string', () => {
    expect(
      parseCustomModelDeleteErrorBody(
        JSON.stringify({
          detail: [{ type: 'value_error', msg: 'bad' }],
          error: 'Human summary',
        }),
      ).detail,
    ).toBe('Human summary');
  });
});

// ---------------------------------------------------------------------------
// deleteCustomModel
// ---------------------------------------------------------------------------

describe('deleteCustomModel', () => {
  it('DELETEs the model and returns on success (204)', async () => {
    mockDELETE.mockResolvedValue({
      error: undefined,
      response: { status: 204, ok: true } as Response,
    });

    await deleteCustomModel('workbench', 'my-model');

    expect(mockDELETE).toHaveBeenCalledWith(
      '/api/projects/{project}/models/{model_name}',
      { params: { path: { project: 'workbench', model_name: 'my-model' } } },
    );
  });

  it('throws without calling the client when project or modelName is empty', async () => {
    await expect(deleteCustomModel('', 'm')).rejects.toThrow(APIRequestError);
    await expect(deleteCustomModel('p', '')).rejects.toThrow(APIRequestError);
    expect(mockDELETE).not.toHaveBeenCalled();
  });

  it('throws CustomModelDeleteConflictError on 409 with parsed blocking services', async () => {
    // openapi-fetch drains the error body into `error` (parsed JSON when
    // possible); the service re-serializes it rather than re-reading the
    // already-consumed response body.
    mockDELETE.mockResolvedValue({
      error: {
        detail: 'Model has active deployments',
        additionalInfo: { blockingServices: ['deploy-a'] },
      },
      response: { status: 409 } as Response,
    });

    await expect(
      deleteCustomModel('workbench', 'my-model'),
    ).rejects.toMatchObject({
      name: 'CustomModelDeleteConflictError',
      statusCode: 409,
      blockingServices: ['deploy-a'],
    });
  });

  it('throws APIRequestError on other error responses', async () => {
    mockDELETE.mockResolvedValue({
      error: { detail: 'missing' },
      response: { status: 404 } as Response,
    });

    await expect(deleteCustomModel('workbench', 'gone')).rejects.toMatchObject({
      statusCode: 404,
    });
  });
});

// ---------------------------------------------------------------------------
// copyCustomModel
// ---------------------------------------------------------------------------

describe('copyCustomModel', () => {
  it('calls the copy endpoint for the given project and source model', async () => {
    mockPOST.mockResolvedValue({
      error: undefined,
      response: { status: 204, ok: true } as Response,
    });

    await copyCustomModel('workbench', 'custom-model-a');

    expect(mockPOST).toHaveBeenCalledWith(
      '/api/projects/{project}/models/{model_name}/copy',
      {
        params: {
          path: { project: 'workbench', model_name: 'custom-model-a' },
        },
      },
    );
  });

  it('throws without calling the client when project is empty', async () => {
    await expect(copyCustomModel('', 'custom-model-a')).rejects.toThrow(
      APIRequestError,
    );
    expect(mockPOST).not.toHaveBeenCalled();
  });

  it('throws without calling the client when source model name is empty', async () => {
    await expect(copyCustomModel('workbench', '')).rejects.toThrow(
      APIRequestError,
    );
    expect(mockPOST).not.toHaveBeenCalled();
  });

  it('throws APIRequestError when the copy request fails', async () => {
    mockPOST.mockResolvedValue({
      error: { detail: 'Model already exists' },
      response: { status: 400 } as Response,
    });

    await expect(
      copyCustomModel('workbench', 'custom-model-a'),
    ).rejects.toThrow(APIRequestError);
  });
});

// ---------------------------------------------------------------------------
// normalizeCustomModelDisplayName
// ---------------------------------------------------------------------------

describe('normalizeCustomModelDisplayName', () => {
  it('trims surrounding whitespace and lowercases', () => {
    expect(normalizeCustomModelDisplayName('  Gemma 3 1B IT  ')).toBe(
      'gemma 3 1b it',
    );
  });

  it('treats case- and whitespace-variant names as equal', () => {
    expect(normalizeCustomModelDisplayName('My Model')).toBe(
      normalizeCustomModelDisplayName('  my model'),
    );
  });
});

// ---------------------------------------------------------------------------
// collectExistingDisplayNames
// ---------------------------------------------------------------------------

describe('collectExistingDisplayNames', () => {
  function aggregatedWith(name: string, resourceName: string) {
    return customModelToAggregatedAIM(
      buildCustomModel({
        metadata: {
          name: resourceName,
          namespace: 'workbench',
          labels: { 'aiwb.apps.eai.amd.com/model-source-type': 'custom' },
          annotations: {
            ...ANNOTATIONS,
            'aiwb.apps.eai.amd.com/model-display-name': name,
          },
          creationTimestamp: '2026-06-08T21:00:00Z',
        },
      }),
    );
  }

  it('collects normalized display names from all models', () => {
    const models = [
      aggregatedWith('Gemma 3 1B IT', 'cr-a'),
      aggregatedWith('Qwen 0.6B', 'cr-b'),
    ];

    const names = collectExistingDisplayNames(models);

    expect(names.has('gemma 3 1b it')).toBe(true);
    expect(names.has('qwen 0.6b')).toBe(true);
    expect(names.size).toBe(2);
  });

  it('excludes the model being edited so its own name is not a duplicate', () => {
    const models = [
      aggregatedWith('Gemma 3 1B IT', 'cr-a'),
      aggregatedWith('Qwen 0.6B', 'cr-b'),
    ];

    const names = collectExistingDisplayNames(models, 'cr-a');

    expect(names.has('gemma 3 1b it')).toBe(false);
    expect(names.has('qwen 0.6b')).toBe(true);
  });
});
