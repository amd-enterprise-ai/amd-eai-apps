// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { vi, beforeEach, describe, it, expect } from 'vitest';

import { listChattableWorkloads } from '@/lib/app/chat';
import { resolveAIMServiceDisplay } from '@/lib/app/aims';
import { resolveCustomProfileDeployments } from '@/lib/app/custom-profiles';
import {
  getInferenceModel,
  listAllInferenceDeployments,
} from '@/lib/app/inference';
import {
  AIM_DISPLAY_NAME_ANNOTATION,
  AIMServiceStatus,
  FINE_TUNED_LABEL,
  NAMESPACE_AIM_MODEL_LABEL,
} from '@/types/aims';
import type { AIMService } from '@/types/aims';

vi.mock('@/lib/app/aims', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/app/aims')>()),
  resolveAIMServiceDisplay: vi.fn(),
}));

vi.mock('@/lib/app/inference', () => ({
  getInferenceModel: vi.fn(),
  listAllInferenceDeployments: vi.fn(),
}));

vi.mock('@/lib/app/custom-profiles', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/app/custom-profiles')>()),
  resolveCustomProfileDeployments: vi.fn().mockResolvedValue(new Map()),
}));

const mockListInferenceDeployments = listAllInferenceDeployments as ReturnType<
  typeof vi.fn
>;
const mockGetInferenceModel = getInferenceModel as ReturnType<typeof vi.fn>;
const mockResolveAIMServiceDisplay = resolveAIMServiceDisplay as ReturnType<
  typeof vi.fn
>;
const mockResolveCustomProfileDeployments =
  resolveCustomProfileDeployments as ReturnType<typeof vi.fn>;

const buildAimService = (overrides: {
  id: string;
  name?: string;
  labels?: Record<string, string>;
  annotations?: Record<string, string>;
  modelRef?: string;
  status?: AIMServiceStatus;
}): AIMService =>
  ({
    id: overrides.id,
    metadata: {
      name: overrides.name ?? overrides.id,
      namespace: 'project1',
      uid: `uid-${overrides.id}`,
      labels: overrides.labels ?? {},
      annotations: overrides.annotations ?? {},
      creationTimestamp: '',
      ownerReferences: [],
    },
    spec: {
      model: { name: overrides.modelRef ?? 'aim-model' },
      replicas: 1,
      routing: { annotations: {}, enabled: false },
      runtimeConfigName: '',
    },
    status: {
      status: overrides.status ?? 'Running',
      resolvedModel: { name: overrides.modelRef ?? 'aim-model' },
      routing: { path: '' },
      endpoints: { internal: '', external: '' },
    },
    statusValue: '',
    endpoints: { internal: '', external: '' },
  }) as AIMService;

describe('listChattableWorkloads', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Default to a 404 for any per-name lookup so tests don't accidentally
    // pull cluster-catalog metadata they didn't set up.
    mockGetInferenceModel.mockRejectedValue(new Error('not found'));
    mockResolveCustomProfileDeployments.mockResolvedValue(new Map());
  });

  it('uses the user-given deploy name for fine-tuned AIM services', async () => {
    const fineTunedService = buildAimService({
      id: 'svc-finetuned',
      labels: { [FINE_TUNED_LABEL]: 'true' },
      annotations: {
        [AIM_DISPLAY_NAME_ANNOTATION]: 'amd-rai-suite-qa-with-refusal-v6',
      },
      modelRef: 'finetuned-model-ref',
    });
    mockListInferenceDeployments.mockResolvedValue([fineTunedService]);
    // For fine-tuned services the resolved title is the base model name, not
    // the user-given deploy name; the deploy name lives in the annotation.
    mockResolveAIMServiceDisplay.mockReturnValue({
      title: 'meta-llama/Llama-3.2-3B-Instruct',
      canonicalName: 'meta-llama/Llama-3.2-3B-Instruct',
      imageVersion: '0.11.0',
      name: 'amd-rai-suite-qa-with-refusal-v6',
      metric: 'throughput',
      tags: [],
    });

    const result = await listChattableWorkloads('project1');

    expect(result.workloads).toHaveLength(1);
    expect(result.workloads[0].displayName).toBe(
      'amd-rai-suite-qa-with-refusal-v6',
    );
  });

  it('uses canonical name fallback for non fine-tuned AIM services', async () => {
    const catalogService = buildAimService({
      id: 'svc-catalog',
      modelRef: 'aim-llama-3.2-3b',
    });
    mockListInferenceDeployments.mockResolvedValue([catalogService]);
    mockResolveAIMServiceDisplay.mockReturnValue({
      title: 'Llama 3.2 3B Instruct',
      canonicalName: 'meta-llama/Llama-3.2-3B-Instruct',
      imageVersion: '0.11.0',
      name: 'aim-llama-3.2-3b',
      metric: 'throughput',
      tags: [],
    });

    const result = await listChattableWorkloads('project1');

    expect(result.workloads).toHaveLength(1);
    expect(result.workloads[0].displayName).toBe(
      'meta-llama/Llama-3.2-3B-Instruct',
    );
  });

  it('uses deploy display name for non fine-tuned AIM services when it differs from resource name', async () => {
    const catalogService = buildAimService({
      id: 'svc-catalog-display',
      name: 'svc-catalog-resource-name',
      annotations: {
        [AIM_DISPLAY_NAME_ANNOTATION]: 'Llama Chat Friendly Name',
      },
      modelRef: 'aim-llama-3.2-3b',
    });
    mockListInferenceDeployments.mockResolvedValue([catalogService]);
    mockResolveAIMServiceDisplay.mockReturnValue({
      title: 'Llama 3.2 3B Instruct',
      canonicalName: 'meta-llama/Llama-3.2-3B-Instruct',
      imageVersion: '0.11.0',
      name: 'aim-llama-3.2-3b',
      metric: 'throughput',
      tags: [],
    });

    const result = await listChattableWorkloads('project1');

    expect(result.workloads).toHaveLength(1);
    expect(result.workloads[0].displayName).toBe('Llama Chat Friendly Name');
  });

  it('fans out per-name catalog lookups, skipping namespace-scoped AIMModel services', async () => {
    const catalogServiceA = buildAimService({
      id: 'svc-a',
      modelRef: 'aim-model-a',
    });
    const catalogServiceB = buildAimService({
      id: 'svc-b',
      modelRef: 'aim-model-b',
    });
    const fineTunedService = buildAimService({
      id: 'svc-ft',
      labels: { [FINE_TUNED_LABEL]: 'true' },
      modelRef: 'ft-model',
    });
    const byomService = buildAimService({
      id: 'svc-byom',
      labels: { [NAMESPACE_AIM_MODEL_LABEL]: 'true' },
      modelRef: 'byom-namespace-model',
    });
    mockListInferenceDeployments.mockResolvedValue([
      catalogServiceA,
      catalogServiceB,
      fineTunedService,
      byomService,
    ]);
    mockResolveAIMServiceDisplay.mockReturnValue({
      title: 'X',
      canonicalName: 'org/x',
      imageVersion: '1.0.0',
      name: 'aim-model-a',
      metric: 'default',
      tags: [],
    });

    await listChattableWorkloads('project1');

    // Only the two cluster-catalog services get per-name lookups;
    // namespace-scoped AIMModel services (fine-tuned and custom-imported) are skipped.
    expect(mockGetInferenceModel).toHaveBeenCalledTimes(2);
    expect(mockGetInferenceModel).toHaveBeenCalledWith('aim-model-a');
    expect(mockGetInferenceModel).toHaveBeenCalledWith('aim-model-b');
    expect(mockGetInferenceModel).not.toHaveBeenCalledWith('ft-model');
    expect(mockGetInferenceModel).not.toHaveBeenCalledWith(
      'byom-namespace-model',
    );
  });

  it('includes namespace-scoped AIMModel services in the chattable workloads list', async () => {
    const byomService = buildAimService({
      id: 'svc-byom',
      labels: { [NAMESPACE_AIM_MODEL_LABEL]: 'true' },
      modelRef: 'byom-namespace-model',
    });
    mockListInferenceDeployments.mockResolvedValue([byomService]);
    mockResolveAIMServiceDisplay.mockReturnValue({
      title: 'My Custom Model',
      canonicalName: 'byom-namespace-model',
      imageVersion: '',
      name: 'byom-namespace-model',
      metric: 'default',
      tags: [],
    });

    const result = await listChattableWorkloads('project1');

    expect(result.workloads).toHaveLength(1);
    expect(result.workloads[0].id).toBe('svc-byom');
    expect(mockGetInferenceModel).not.toHaveBeenCalled();
  });

  it('labels a custom-model deployment with the profile it was deployed with', async () => {
    const byomService = buildAimService({
      id: 'svc-byom',
      labels: { [NAMESPACE_AIM_MODEL_LABEL]: 'true' },
      modelRef: 'byom-namespace-model',
    });
    mockListInferenceDeployments.mockResolvedValue([byomService]);
    // A pinned custom profile carries no selector, so the metric falls back to
    // 'default' — the label is what must reach the dropdown instead.
    mockResolveAIMServiceDisplay.mockReturnValue({
      title: 'My Custom Model',
      canonicalName: 'byom-namespace-model',
      imageVersion: '',
      name: 'byom-namespace-model',
      metric: 'default',
      tags: [],
    });
    mockResolveCustomProfileDeployments.mockResolvedValue(
      new Map([
        [
          'svc-byom',
          {
            displayName: 'High speed',
            profile: {
              metric: 'latency',
              gpu: 'MI300X',
              templateGpuCount: 2,
              acceleratorType: 'gpu',
              precision: 'fp8',
            },
          },
        ],
      ]),
    );

    const result = await listChattableWorkloads('project1');

    expect(result.workloadDisplayInfo['svc-byom'].profileDisplayName).toBe(
      'High speed',
    );
  });

  it('leaves non-custom deployments without a profile label', async () => {
    const catalogService = buildAimService({
      id: 'svc-catalog',
      modelRef: 'aim-llama-3.2-3b',
    });
    mockListInferenceDeployments.mockResolvedValue([catalogService]);
    mockResolveAIMServiceDisplay.mockReturnValue({
      title: 'Llama 3.2 3B Instruct',
      canonicalName: 'meta-llama/Llama-3.2-3B-Instruct',
      imageVersion: '0.11.0',
      name: 'aim-llama-3.2-3b',
      metric: 'throughput',
      tags: [],
    });

    const result = await listChattableWorkloads('project1');

    expect(
      result.workloadDisplayInfo['svc-catalog'].profileDisplayName,
    ).toBeUndefined();
  });

  it('tolerates per-name fetch failures via Promise.allSettled', async () => {
    const catalogServiceA = buildAimService({
      id: 'svc-a',
      modelRef: 'aim-model-a',
    });
    const catalogServiceB = buildAimService({
      id: 'svc-b',
      modelRef: 'aim-model-b',
    });
    mockListInferenceDeployments.mockResolvedValue([
      catalogServiceA,
      catalogServiceB,
    ]);
    // One fetch succeeds, one 404s — must not blank the whole result.
    mockGetInferenceModel
      .mockResolvedValueOnce({
        metadata: { name: 'aim-model-a', annotations: {}, labels: {} },
        spec: { image: 'img' },
        status: { status: 'Ready', imageMetadata: { model: {}, oci: {} } },
      })
      .mockRejectedValueOnce(new Error('boom'));
    mockResolveAIMServiceDisplay.mockReturnValue({
      title: 'Y',
      canonicalName: 'org/y',
      imageVersion: '1.0',
      name: 'aim-model-a',
      metric: 'default',
      tags: [],
    });

    const result = await listChattableWorkloads('project1');

    expect(result.workloads).toHaveLength(2);
  });

  it('falls back to modelRef for fine-tuned services without a title', async () => {
    const fineTunedService = buildAimService({
      id: 'svc-finetuned-bare',
      labels: { [FINE_TUNED_LABEL]: 'true' },
      modelRef: 'bare-model-ref',
    });
    mockListInferenceDeployments.mockResolvedValue([fineTunedService]);
    mockResolveAIMServiceDisplay.mockReturnValue({
      title: '',
      canonicalName: 'meta-llama/Llama-3.2-3B-Instruct',
      imageVersion: '',
      name: 'bare-model-ref',
      metric: 'default',
      tags: [],
    });

    const result = await listChattableWorkloads('project1');

    expect(result.workloads[0].displayName).toBe('bare-model-ref');
  });

  it('excludes workloads that are not running inference', async () => {
    const runningService = buildAimService({ id: 'svc-running' });
    const pendingService = buildAimService({
      id: 'svc-pending',
      status: 'Pending',
    });
    mockListInferenceDeployments.mockResolvedValue([
      runningService,
      pendingService,
    ]);
    mockResolveAIMServiceDisplay.mockReturnValue({
      title: 'Running',
      canonicalName: 'org/model',
      imageVersion: '1.0',
      name: 'model',
      metric: 'throughput',
      tags: [],
    });

    const result = await listChattableWorkloads('project1');

    expect(result.workloads).toHaveLength(1);
    expect(result.workloads.map((w) => w.id)).toEqual(['svc-running']);
  });
});
