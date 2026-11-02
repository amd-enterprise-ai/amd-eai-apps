// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  createCustomProfile,
  customModelNamesFromServices,
  customModelServices,
  CustomProfileConflictError,
  deleteCustomProfile,
  listCustomProfiles,
  resolveCustomProfileDeployments,
  updateCustomProfile,
  type CustomProfileCreateRequest,
  type CustomProfileResponse,
} from '@/lib/app/custom-profiles';
import {
  FINE_TUNED_LABEL,
  NAMESPACE_AIM_MODEL_LABEL,
  type AIMService,
} from '@/types/aims';

// The list and create calls ride the typed client, so they are asserted against
// the generated path/param contract. Update and delete still use raw fetch:
// their upstream endpoints are not in the OpenAPI schema yet, so there is no
// generated path to type the typed client against.
const mockGET = vi.fn();
const mockPOST = vi.fn();

vi.mock('@/lib/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api-client')>();
  return {
    ...actual,
    apiClient: {
      GET: (...args: unknown[]) => mockGET(...args),
      POST: (...args: unknown[]) => mockPOST(...args),
    },
  };
});

const mockFetch = vi.fn();
global.fetch = mockFetch;

const okData = <T>(data: T) => ({
  data,
  error: undefined,
  response: { status: 200 } as Response,
});

const clientError = (status: number, detail = 'upstream') => ({
  data: undefined,
  error: { detail },
  response: { status, statusText: detail } as Response,
});

const okResponse = <T>(body: T) => ({
  ok: true,
  status: 200,
  json: () => Promise.resolve(body),
});

const errorResponse = (status: number, body = 'upstream') => ({
  ok: false,
  status,
  text: () => Promise.resolve(body),
  json: () => Promise.resolve({ error: body }),
});

const defaultProfile: CustomProfileResponse = {
  name: 'default',
  displayName: 'Default',
  isDefault: true,
  resourceName: 'llama-3-8b-default',
  createdAt: '2026-07-02T11:04:19Z',
  inUseBy: [],
};

const namedProfile: CustomProfileResponse = {
  name: 'llama-3-8b-high-speed-7f3b6c8e',
  displayName: 'High speed',
  isDefault: false,
  resourceName: 'llama-3-8b-high-speed-7f3b6c8e',
  createdAt: '2026-07-18T09:22:41Z',
  createdBy: 'user@example.com',
  inUseBy: [{ serviceId: 'svc-1', displayName: 'summarizer-prod' }],
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('listCustomProfiles', () => {
  it('rejects a missing project without calling the API', async () => {
    await expect(listCustomProfiles('', 'model-a')).rejects.toMatchObject({
      statusCode: 422,
    });
    expect(mockGET).not.toHaveBeenCalled();
  });

  it('rejects a missing model without calling the API', async () => {
    await expect(listCustomProfiles('team-alpha', '')).rejects.toMatchObject({
      statusCode: 422,
    });
    expect(mockGET).not.toHaveBeenCalled();
  });

  it('GETs the nested profiles route with the project and model as path params', async () => {
    mockGET.mockResolvedValueOnce(okData({ data: [defaultProfile] }));

    await listCustomProfiles('team-alpha', 'model-a');

    expect(mockGET).toHaveBeenCalledWith(
      '/api/projects/{project}/models/{model}/profiles',
      { params: { path: { project: 'team-alpha', model: 'model-a' } } },
    );
  });

  it('unwraps the list envelope, preserving Default-first order', async () => {
    mockGET.mockResolvedValueOnce(
      okData({ data: [defaultProfile, namedProfile] }),
    );

    const profiles = await listCustomProfiles('team-alpha', 'model-a');

    expect(profiles.map((profile) => profile.name)).toEqual([
      'default',
      'llama-3-8b-high-speed-7f3b6c8e',
    ]);
  });

  it('returns the single Default entry for a model with no named profiles', async () => {
    mockGET.mockResolvedValueOnce(okData({ data: [defaultProfile] }));

    const profiles = await listCustomProfiles('team-alpha', 'model-a');

    expect(profiles).toHaveLength(1);
    expect(profiles[0].isDefault).toBe(true);
  });

  it('treats a missing data envelope as an empty list', async () => {
    mockGET.mockResolvedValueOnce(okData({ data: undefined }));

    await expect(listCustomProfiles('team-alpha', 'model-a')).resolves.toEqual(
      [],
    );
  });

  it('throws APIRequestError carrying the upstream status', async () => {
    mockGET.mockResolvedValueOnce(clientError(404));

    await expect(
      listCustomProfiles('team-alpha', 'missing'),
    ).rejects.toMatchObject({ statusCode: 404 });
  });
});

describe('deleteCustomProfile', () => {
  it('rejects a missing profile without calling the API', async () => {
    await expect(
      deleteCustomProfile('team-alpha', 'model-a', ''),
    ).rejects.toMatchObject({ statusCode: 422 });
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('DELETEs the single-profile route and resolves on 204', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, status: 204 });

    await expect(
      deleteCustomProfile('team-alpha', 'model-a', 'profile-1'),
    ).resolves.toBeUndefined();

    const [url, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(
      '/api/projects/team-alpha/models/model-a/profiles/profile-1',
    );
    expect(init.method).toBe('DELETE');
  });

  it('surfaces a 409 as a conflict error naming the blocking deployments', async () => {
    mockFetch.mockResolvedValueOnce(
      errorResponse(
        409,
        JSON.stringify({
          detail: "Profile 'High speed' is in use by 1 deployment.",
          additionalInfo: {
            blockingServices: [
              { serviceId: 'svc-1', displayName: 'summarizer-prod' },
            ],
          },
        }),
      ),
    );

    const error = await deleteCustomProfile(
      'team-alpha',
      'model-a',
      'profile-1',
    ).catch((e: unknown) => e);

    expect(error).toBeInstanceOf(CustomProfileConflictError);
    expect(error).toMatchObject({
      statusCode: 409,
      blockingServices: ['summarizer-prod'],
    });
  });

  it('throws APIRequestError for the 422 returned when deleting Default', async () => {
    mockFetch.mockResolvedValueOnce(
      errorResponse(
        422,
        JSON.stringify({ detail: 'The Default profile cannot be deleted.' }),
      ),
    );

    await expect(
      deleteCustomProfile('team-alpha', 'model-a', 'default'),
    ).rejects.toMatchObject({ statusCode: 422 });
  });

  it('throws APIRequestError for an already-deleted profile', async () => {
    mockFetch.mockResolvedValueOnce(
      errorResponse(404, JSON.stringify({ detail: 'Profile not found.' })),
    );

    await expect(
      deleteCustomProfile('team-alpha', 'model-a', 'gone'),
    ).rejects.toMatchObject({ statusCode: 404 });
  });
});

const createRequest: CustomProfileCreateRequest = {
  displayName: 'High speed',
  acceleratorModel: 'MI300X',
  acceleratorCount: 8,
  precision: 'fp8',
  metric: 'latency',
  image: 'amdenterpriseai/aim-base:0.11',
  customProfile: {
    acceleratorType: 'gpu',
    engineArgs: { 'max-model-len': 32768 },
  },
};

describe('createCustomProfile', () => {
  it('rejects a blank profile name without calling the API', async () => {
    await expect(
      createCustomProfile('team-alpha', 'model-a', {
        ...createRequest,
        displayName: '   ',
      }),
    ).rejects.toMatchObject({ statusCode: 422 });
    expect(mockPOST).not.toHaveBeenCalled();
  });

  it('rejects a missing project without calling the API', async () => {
    await expect(
      createCustomProfile('', 'model-a', createRequest),
    ).rejects.toMatchObject({ statusCode: 422 });
    expect(mockPOST).not.toHaveBeenCalled();
  });

  it('POSTs the request to the collection route', async () => {
    mockPOST.mockResolvedValueOnce(okData(namedProfile));

    const created = await createCustomProfile(
      'team-alpha',
      'model-a',
      createRequest,
    );

    expect(mockPOST).toHaveBeenCalledWith(
      '/api/projects/{project}/models/{model}/profiles',
      {
        params: { path: { project: 'team-alpha', model: 'model-a' } },
        body: createRequest,
      },
    );
    expect(created.name).toBe('llama-3-8b-high-speed-7f3b6c8e');
  });

  it('surfaces a duplicate name as a conflict error with no blocking deployments', async () => {
    mockPOST.mockResolvedValueOnce(
      clientError(409, "A profile named 'High speed' exists."),
    );

    const error = await createCustomProfile(
      'team-alpha',
      'model-a',
      createRequest,
    ).catch((e: unknown) => e);

    expect(error).toBeInstanceOf(CustomProfileConflictError);
    expect(error).toMatchObject({ statusCode: 409, blockingServices: [] });
  });

  it('names the blocking deployments when the axes collide with a live one', async () => {
    mockPOST.mockResolvedValueOnce({
      data: undefined,
      error: {
        detail: 'Profile is in use.',
        additionalInfo: [{ displayName: 'summarizer-prod' }],
      },
      response: { status: 409, statusText: 'Conflict' } as Response,
    });

    const error = await createCustomProfile(
      'team-alpha',
      'model-a',
      createRequest,
    ).catch((e: unknown) => e);

    expect(error).toMatchObject({
      statusCode: 409,
      blockingServices: ['summarizer-prod'],
    });
  });

  it('throws APIRequestError for the 422 returned for a reserved name', async () => {
    mockPOST.mockResolvedValueOnce(
      clientError(422, "'Default' is a reserved profile name."),
    );

    await expect(
      createCustomProfile('team-alpha', 'model-a', {
        ...createRequest,
        displayName: 'Default',
      }),
    ).rejects.toMatchObject({ statusCode: 422 });
  });
});

describe('updateCustomProfile', () => {
  it('rejects a missing profile without calling the API', async () => {
    await expect(
      updateCustomProfile('team-alpha', 'model-a', '', {
        displayName: 'Renamed',
      }),
    ).rejects.toMatchObject({ statusCode: 422 });
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('rejects an empty patch body without calling the API', async () => {
    await expect(
      updateCustomProfile('team-alpha', 'model-a', 'profile-1', {}),
    ).rejects.toMatchObject({ statusCode: 400 });
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('PATCHes the single-profile route with encoded params', async () => {
    mockFetch.mockResolvedValueOnce(okResponse(namedProfile));

    const updated = await updateCustomProfile(
      'team-alpha',
      'model-a',
      'prof/1',
      { displayName: 'High speed v2' },
    );

    const [url, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(
      '/api/projects/team-alpha/models/model-a/profiles/prof%2F1',
    );
    expect(init.method).toBe('PATCH');
    expect(JSON.parse(String(init.body))).toEqual({
      displayName: 'High speed v2',
    });
    expect(updated.displayName).toBe('High speed');
  });

  it('sends an explicit null to reset a cleared configuration field', async () => {
    mockFetch.mockResolvedValueOnce(okResponse(namedProfile));

    await updateCustomProfile('team-alpha', 'model-a', 'profile-1', {
      customProfile: { engineArgs: null, engineEnv: null },
    });

    const [, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({
      customProfile: { engineArgs: null, engineEnv: null },
    });
  });

  it('surfaces the in-use refusal as a conflict error naming the deployments', async () => {
    mockFetch.mockResolvedValueOnce(
      errorResponse(
        409,
        JSON.stringify({
          detail: "Profile 'High speed' is in use by 1 deployment.",
          additionalInfo: {
            blockingServices: [
              { serviceId: 'svc-1', displayName: 'summarizer-prod' },
            ],
          },
        }),
      ),
    );

    const error = await updateCustomProfile(
      'team-alpha',
      'model-a',
      'profile-1',
      { displayName: 'High speed v2' },
    ).catch((e: unknown) => e);

    expect(error).toBeInstanceOf(CustomProfileConflictError);
    expect(error).toMatchObject({
      statusCode: 409,
      blockingServices: ['summarizer-prod'],
    });
  });

  it('throws APIRequestError for the 422 returned when patching Default', async () => {
    mockFetch.mockResolvedValueOnce(
      errorResponse(
        422,
        JSON.stringify({
          detail: 'Edit the Default through the model settings route.',
        }),
      ),
    );

    await expect(
      updateCustomProfile('team-alpha', 'model-a', 'default', {
        displayName: 'Renamed',
      }),
    ).rejects.toMatchObject({ statusCode: 422 });
  });
});

const buildService = (
  id: string,
  modelName: string,
  labels: Record<string, string>,
): AIMService =>
  ({
    id,
    metadata: { name: id, labels, annotations: {} },
    spec: { model: { name: modelName } },
  }) as AIMService;

describe('customModelServices', () => {
  it('keeps custom-model deployments and drops fine-tuned and catalog ones', () => {
    const custom = buildService('svc-1', 'model-a', {
      [NAMESPACE_AIM_MODEL_LABEL]: 'true',
    });
    const services = [
      custom,
      buildService('svc-ft', 'ft-model', {
        [NAMESPACE_AIM_MODEL_LABEL]: 'true',
        [FINE_TUNED_LABEL]: 'true',
      }),
      buildService('svc-catalog', 'aim-llama-3.2-3b', {}),
    ];

    expect(customModelServices(services)).toEqual([custom]);
  });
});

describe('customModelNamesFromServices', () => {
  it('collects the model names of custom-model deployments, deduped', () => {
    const services = [
      buildService('svc-1', 'model-a', {
        [NAMESPACE_AIM_MODEL_LABEL]: 'true',
      }),
      buildService('svc-2', 'model-a', {
        [NAMESPACE_AIM_MODEL_LABEL]: 'true',
      }),
      buildService('svc-3', 'model-b', {
        [NAMESPACE_AIM_MODEL_LABEL]: 'true',
      }),
    ];

    expect(customModelNamesFromServices(services)).toEqual([
      'model-a',
      'model-b',
    ]);
  });

  it('excludes fine-tuned and cluster-catalog deployments', () => {
    const services = [
      // Fine-tuned deployments carry the namespace label too, but have no
      // selectable profiles, so the profiles endpoint does not apply to them.
      buildService('svc-ft', 'ft-model', {
        [NAMESPACE_AIM_MODEL_LABEL]: 'true',
        [FINE_TUNED_LABEL]: 'true',
      }),
      buildService('svc-catalog', 'aim-llama-3.2-3b', {}),
    ];

    expect(customModelNamesFromServices(services)).toEqual([]);
  });
});

describe('resolveCustomProfileDeployments', () => {
  const readyProfile: CustomProfileResponse = {
    ...namedProfile,
    inUseBy: [{ serviceId: 'svc-1', displayName: 'summarizer-prod' }],
    profile: {
      metadata: { name: 'llama-3-8b-high-speed-abc' },
      spec: {
        metric: 'latency',
        acceleratorModel: 'MI300X',
        acceleratorCount: 2,
        acceleratorType: 'gpu',
        precision: 'fp8',
      },
    },
  } as CustomProfileResponse;

  it('keys the pinned profile label and axes by deployment id', async () => {
    mockGET.mockResolvedValueOnce(okData({ data: [readyProfile] }));

    const result = await resolveCustomProfileDeployments('team-alpha', [
      'model-a',
    ]);

    expect(result.get('svc-1')).toEqual({
      displayName: 'High speed',
      profile: {
        metric: 'latency',
        gpu: 'MI300X',
        templateGpuCount: 2,
        acceleratorType: 'gpu',
        precision: 'fp8',
      },
    });
  });

  it('maps every deployment sharing a profile', async () => {
    mockGET.mockResolvedValueOnce(
      okData({
        data: [
          {
            ...readyProfile,
            inUseBy: [
              { serviceId: 'svc-1', displayName: 'one' },
              { serviceId: 'svc-2', displayName: 'two' },
            ],
          },
        ],
      }),
    );

    const result = await resolveCustomProfileDeployments('team-alpha', [
      'model-a',
    ]);

    expect(result.get('svc-1')?.displayName).toBe('High speed');
    expect(result.get('svc-2')?.displayName).toBe('High speed');
  });

  it('omits profiles no deployment references', async () => {
    mockGET.mockResolvedValueOnce(okData({ data: [defaultProfile] }));

    const result = await resolveCustomProfileDeployments('team-alpha', [
      'model-a',
    ]);

    expect(result.size).toBe(0);
  });

  it('keeps the other models when one model cannot be read', async () => {
    mockGET
      .mockResolvedValueOnce(clientError(404))
      .mockResolvedValueOnce(okData({ data: [readyProfile] }));

    const result = await resolveCustomProfileDeployments('team-alpha', [
      'missing',
      'model-a',
    ]);

    expect(result.get('svc-1')?.displayName).toBe('High speed');
  });

  it('makes no request when there are no custom models', async () => {
    const result = await resolveCustomProfileDeployments('team-alpha', []);

    expect(result.size).toBe(0);
    expect(mockGET).not.toHaveBeenCalled();
  });
});
