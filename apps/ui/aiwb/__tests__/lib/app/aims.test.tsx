// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  buildFilteredCatalog,
  transformToAggregatedAIMs,
  resolveAILabName,
  aimParser,
  resolveAIMServiceDisplay,
  getAIMServiceStatusVariants,
  getModelCapability,
  getInferenceApiPath,
} from '@/lib/app/aims';
import { IconCircleCaretRight } from '@tabler/icons-react';
import {
  AIMServiceStatus,
  AIMWorkloadStatus,
  ParsedAIM,
  AIMClusterModel,
  AIMService,
} from '@/types/aims';

describe('getAIMServiceStatusVariants', () => {
  const t = (key: string) => key;

  it('maps RUNNING to primary color with play icon', () => {
    const variants = getAIMServiceStatusVariants(t);
    const running = variants['Running'];
    expect(running.color).toBe('primary');
    expect(running.icon).toBe(IconCircleCaretRight);
    expect(running.intent).toBeUndefined();
  });
});

describe('getModelCapability', () => {
  it.each(['transcription', 'speech-to-text', 'automatic-speech-recognition'])(
    'classifies a model tagged "%s" as transcription',
    (tag) => {
      expect(getModelCapability([tag])).toBe('transcription');
    },
  );

  it('classifies a chat-tagged model as chat', () => {
    expect(getModelCapability(['chat'])).toBe('chat');
  });

  it('defaults to chat when tags are missing or empty', () => {
    expect(getModelCapability(undefined)).toBe('chat');
    expect(getModelCapability([])).toBe('chat');
  });

  it('detects transcription among other tags', () => {
    expect(getModelCapability(['audio', 'speech-to-text', 'preview'])).toBe(
      'transcription',
    );
  });

  it('matches tags exactly (case-sensitive, mirroring the backend frozenset)', () => {
    expect(getModelCapability(['Transcription'])).toBe('chat');
    expect(getModelCapability(['Speech-To-Text'])).toBe('chat');
  });
});

describe('getInferenceApiPath', () => {
  it('returns the audio transcriptions path for transcription', () => {
    expect(getInferenceApiPath('transcription')).toBe(
      '/v1/audio/transcriptions',
    );
  });

  it('returns the chat completions path for chat', () => {
    expect(getInferenceApiPath('chat')).toBe('/v1/chat/completions');
  });
});

describe('aims utility functions', () => {
  describe('resolveAILabName', () => {
    it('maps meta-llama to Meta', () => {
      expect(resolveAILabName('meta-llama/Llama-3.1-8B')).toBe('Meta');
    });

    it('maps mistralai to Mistral AI', () => {
      expect(resolveAILabName('mistralai/Mixtral-8x7B')).toBe('Mistral AI');
    });

    it('maps Qwen to Alibaba Cloud', () => {
      expect(resolveAILabName('Qwen/Qwen-14B')).toBe('Alibaba Cloud');
    });

    it('maps CohereLabs to Cohere', () => {
      expect(resolveAILabName('CohereLabs/command-r')).toBe('Cohere');
    });

    it('maps openai to OpenAI', () => {
      expect(resolveAILabName('openai/gpt-4')).toBe('OpenAI');
    });

    it('returns prefix as-is for unknown labs', () => {
      expect(resolveAILabName('unknown-lab/model-name')).toBe('unknown-lab');
    });

    it('handles model names without slash', () => {
      expect(resolveAILabName('standalone-model')).toBe('standalone-model');
    });
  });

  describe('resolveAIMServiceDisplay', () => {
    const createMockAIMService = (
      overrides: Partial<{
        id: string | null;
        'spec.model.name': string;
        'spec.profile.selector.metric': string;
      }> = {},
    ): AIMService => {
      const modelName = overrides['spec.model.name'] ?? 'aim-test-model';
      return {
        id: overrides.id ?? 'aim-1',
        metadata: {
          name: 'aim-1',
          namespace: 'project1',
          uid: 'uid-1',
          labels: {},
          annotations: {},
          creationTimestamp: '',
          ownerReferences: [],
        },
        spec: {
          model: { name: modelName },
          replicas: 1,
          profile: {
            name: 'mock-profile',
            selector: { metric: overrides['spec.profile.selector.metric'] },
          },
          routing: { annotations: {}, enabled: false },
          runtimeConfigName: '',
        },
        status: {
          status: 'Running',
          resolvedModel: { name: modelName },
          routing: { path: '' },
          endpoints: { internal: '', external: '' },
        },
        endpoints: { internal: '', external: '' },
      } as AIMService;
    };

    const createMockParsedAIM = (
      overrides: Partial<ParsedAIM> = {},
    ): ParsedAIM => ({
      model: 'aim-test-model',
      aimId: 'org/test-model',
      imageReference: 'img:1.0',
      annotations: {
        'aim.eai.amd.com/source-registry': '',
        'aim.eai.amd.com/source-repository': '',
        'aim.eai.amd.com/source-tag': '',
      },
      description: { short: '', full: '' },
      title: 'Test Model Title',
      imageVersion: '1.2.3',
      canonicalName: 'org/test-model',
      tags: [],
      status: 'Ready',
      workloadStatuses: [],
      isPreview: false,
      isHfTokenRequired: false,
      ...overrides,
    });

    it('returns title, canonicalName, and imageVersion from matching ParsedAIM', () => {
      const aimService = createMockAIMService();
      const parsedAIMs = [
        createMockParsedAIM({
          model: 'aim-test-model',
          title: 'Llama 3.1 8B',
          canonicalName: 'meta-llama/Llama-3.1-8B',
          imageVersion: '2.0.0',
        }),
      ];

      const result = resolveAIMServiceDisplay(aimService, parsedAIMs);

      expect(result.title).toBe('Llama 3.1 8B');
      expect(result.canonicalName).toBe('meta-llama/Llama-3.1-8B');
      expect(result.imageVersion).toBe('2.0.0');
      expect(result.name).toBe('aim-test-model');
    });

    it('falls back to resolvedModel.name when no ParsedAIM matches', () => {
      const aimService = createMockAIMService({
        'spec.model.name': 'other-model',
      });
      const parsedAIMs = [createMockParsedAIM({ model: 'aim-test-model' })];

      const result = resolveAIMServiceDisplay(aimService, parsedAIMs);

      expect(result.title).toBe('other-model');
      expect(result.canonicalName).toBe('other-model');
      expect(result.imageVersion).toBe('');
      expect(result.name).toBe('other-model');
    });

    it('falls back to metadata.name when parsedAIMs is undefined', () => {
      const aimService = createMockAIMService({
        'spec.model.name': 'standalone',
      });

      const result = resolveAIMServiceDisplay(aimService);

      expect(result.title).toBe('standalone');
      expect(result.canonicalName).toBe('standalone');
      expect(result.imageVersion).toBe('');
      expect(result.name).toBe('standalone');
    });

    it('returns throughput metric when spec.profile.selector.metric is throughput', () => {
      const aimService = createMockAIMService({
        'spec.profile.selector.metric': 'throughput',
      });

      const result = resolveAIMServiceDisplay(aimService, []);

      expect(result.metric).toBe('throughput');
    });

    it('returns latency metric when spec.profile.selector.metric is latency', () => {
      const aimService = createMockAIMService({
        'spec.profile.selector.metric': 'latency',
      });

      const result = resolveAIMServiceDisplay(aimService, []);

      expect(result.metric).toBe('latency');
    });

    it('returns default metric when spec.profile.selector.metric is missing or unknown', () => {
      const aimServiceNoOverride = createMockAIMService({});
      const aimServiceUnknown = createMockAIMService({
        'spec.profile.selector.metric': 'unknown',
      });

      expect(resolveAIMServiceDisplay(aimServiceNoOverride, []).metric).toBe(
        'default',
      );
      expect(resolveAIMServiceDisplay(aimServiceUnknown, []).metric).toBe(
        'default',
      );
    });

    it('falls back to metadata.name when both model.name and resolvedModel are absent', () => {
      const aimService: AIMService = {
        id: 'aim-orphan',
        metadata: {
          name: 'orphan-service',
          namespace: 'project1',
          uid: 'uid-o',
          labels: {},
          annotations: {},
          creationTimestamp: '',
          ownerReferences: [],
        },
        spec: {
          model: { image: 'repo/model:1.0' },
          replicas: 1,
          routing: { annotations: {}, enabled: false },
          runtimeConfigName: '',
        },
        status: { status: 'Pending' },
        endpoints: { internal: '', external: '' },
      };

      const result = resolveAIMServiceDisplay(aimService);

      expect(result.name).toBe('orphan-service');
      expect(result.title).toBe('orphan-service');
    });

    it('returns AIMServiceDisplayInfo with all required fields', () => {
      const aimService = createMockAIMService({
        'spec.model.name': 'my-aim',
        'spec.profile.selector.metric': 'latency',
      });
      const parsedAIMs = [
        createMockParsedAIM({
          model: 'my-aim',
          title: 'My Model',
          canonicalName: 'org/my-aim',
          imageVersion: '1.0.0',
        }),
      ];

      const result = resolveAIMServiceDisplay(aimService, parsedAIMs);

      expect(result).toEqual({
        title: 'My Model',
        canonicalName: 'org/my-aim',
        imageVersion: '1.0.0',
        name: 'my-aim',
        metric: 'latency',
        tags: [],
      });
    });
  });

  describe('aimParser', () => {
    const createMockAIM = (
      overrides?: Partial<AIMClusterModel>,
    ): AIMClusterModel => ({
      metadata: {
        name: 'test-aim',
        namespace: null,
        uid: 'uid-123',
        labels: {},
        annotations: {
          'aim.eai.amd.com/source-registry': 'docker.io',
          'aim.eai.amd.com/source-repository': 'amdenterpriseai/test-model',
          'aim.eai.amd.com/source-tag': '1.0.0',
        },
        creationTimestamp: '2023-01-01T00:00:00Z',
        ownerReferences: [],
      },
      spec: {
        image: 'docker.io/amdenterpriseai/test-model:1.0.0',
      },
      status: {
        status: 'Ready' as any,
        imageMetadata: {
          model: {
            canonicalName: 'test/model',
            descriptionFull: 'Full description',
            hfTokenRequired: false,
            source: 'https://example.com',
            tags: ['test'],
            title: 'Test Model',
            variants: [],
          },
          oci: {
            description: 'Short description',
            version: '1.0.0',
            title: 'Test Model',
            licenses: 'MIT',
            vendor: 'Test Vendor',
            authors: 'Test Author',
            source: 'https://github.com/example/model',
            documentation: 'https://docs.example.com',
            created: '2023-01-01T00:00:00Z',
            revision: 'abc123',
          },
        },
      },
      ...overrides,
    });

    const createMockService = (
      status: AIMServiceStatus = 'Running',
    ): AIMService => ({
      id: 'service-123',
      metadata: {
        name: 'test-service',
        namespace: 'test-namespace',
        uid: 'uid-456',
        labels: {},
        annotations: {},
        creationTimestamp: '2023-01-01T00:00:00Z',
        ownerReferences: [],
      },
      spec: {
        model: {
          name: 'test-aim',
        },
        replicas: 1,
        routing: {
          annotations: {},
          enabled: true,
        },
        runtimeConfigName: 'default',
      },
      status: {
        status,
      },
      endpoints: {
        internal: 'http://test-service.test-namespace.svc.cluster.local',
        external: 'https://api.example.com/test-namespace/service-123',
      },
    });

    it('parses AIM with no deployed services', () => {
      const aim = createMockAIM();
      const parsed = aimParser(aim);

      expect(parsed.title).toBe('Test Model');
      expect(parsed.canonicalName).toBe('test/model');
      expect(parsed.workloadStatuses).toEqual([AIMWorkloadStatus.NOT_DEPLOYED]);
      expect(parsed.deployedServices).toBeUndefined();
    });

    it('parses AIM with single deployed service', () => {
      const aim = createMockAIM();
      const service = createMockService('Running');
      const parsed = aimParser(aim, [service]);

      expect(parsed.workloadStatuses).toEqual([AIMWorkloadStatus.DEPLOYED]);
      expect(parsed.deployedService).toEqual(service);
    });

    it('parses AIM with multiple deployed services', () => {
      const aim = createMockAIM();
      const services = [
        createMockService('Running'),
        createMockService('Pending'),
      ];
      const parsed = aimParser(aim, services);

      expect(parsed.workloadStatuses).toEqual([
        AIMWorkloadStatus.DEPLOYED,
        AIMWorkloadStatus.PENDING,
      ]);
      expect(parsed.deployedServices).toEqual(services);
    });

    it('maps RUNNING status to DEPLOYED', () => {
      const aim = createMockAIM();
      const service = createMockService('Running');
      const parsed = aimParser(aim, [service]);

      expect(parsed.workloadStatuses).toContain(AIMWorkloadStatus.DEPLOYED);
    });

    it('maps PENDING status to PENDING', () => {
      const aim = createMockAIM();
      const service = createMockService('Pending');
      const parsed = aimParser(aim, [service]);

      expect(parsed.workloadStatuses).toContain(AIMWorkloadStatus.PENDING);
    });

    it('maps STARTING status to STARTING', () => {
      const aim = createMockAIM();
      const service = createMockService('Starting');
      const parsed = aimParser(aim, [service]);

      expect(parsed.workloadStatuses).toContain(AIMWorkloadStatus.STARTING);
    });

    it('maps FAILED status to FAILED', () => {
      const aim = createMockAIM();
      const service = createMockService('Failed');
      const parsed = aimParser(aim, [service]);

      expect(parsed.workloadStatuses).toContain(AIMWorkloadStatus.FAILED);
    });

    it('maps DEGRADED status to DEGRADED', () => {
      const aim = createMockAIM();
      const service = createMockService('Degraded');
      const parsed = aimParser(aim, [service]);

      expect(parsed.workloadStatuses).toContain(AIMWorkloadStatus.DEGRADED);
    });

    it('detects preview versions with preview tag', () => {
      const aim = createMockAIM({
        status: {
          status: 'Ready' as any,
          imageMetadata: {
            model: {
              canonicalName: 'test/model',
              hfTokenRequired: false,
              source: 'https://example.com',
              tags: ['test', 'preview'],
              title: 'Test Model',
              variants: [],
            },
            oci: {} as any,
          },
        },
      });
      const parsed = aimParser(aim);

      expect(parsed.isPreview).toBe(true);
    });

    it('handles empty deployedServices array', () => {
      const aim = createMockAIM();
      const parsed = aimParser(aim, []);

      expect(parsed.workloadStatuses).toEqual([AIMWorkloadStatus.NOT_DEPLOYED]);
      expect(parsed.deployedServices).toEqual([]);
    });

    it('extracts HF token requirement correctly', () => {
      const aim = createMockAIM({
        status: {
          status: 'Ready' as any,
          imageMetadata: {
            model: {
              canonicalName: 'test/model',
              hfTokenRequired: true,
              source: 'https://example.com',
              tags: ['test'],
              title: 'Test Model',
              variants: [],
            },
            oci: {} as any,
          },
        },
      });
      const parsed = aimParser(aim);

      expect(parsed.isHfTokenRequired).toBe(true);
    });

    it('marks AIMs without onboarding annotations as non-custom imports', () => {
      const aim = createMockAIM();
      const parsed = aimParser(aim);

      expect(parsed.isCustomImport).toBe(false);
      expect(parsed.sourceUri).toBeUndefined();
    });

    it('flags AIMs with the source-uri annotation as custom imports', () => {
      const aim = createMockAIM({
        metadata: {
          name: 'test-aim',
          namespace: null,
          uid: 'uid-123',
          labels: {},
          annotations: {
            'aim.eai.amd.com/source-registry': 'docker.io',
            'aim.eai.amd.com/source-repository': 'amdenterpriseai/test-model',
            'aim.eai.amd.com/source-tag': '1.0.0',
            'airm.silogen.ai/source-uri':
              'https://huggingface.co/meta-llama/Llama-3-8B',
          },
          creationTimestamp: '2023-01-01T00:00:00Z',
          ownerReferences: [],
        },
      });
      const parsed = aimParser(aim);

      expect(parsed.isCustomImport).toBe(true);
      expect(parsed.sourceUri).toBe(
        'https://huggingface.co/meta-llama/Llama-3-8B',
      );
    });

    it('flags AIMs with only the model-display-name annotation as custom imports', () => {
      const aim = createMockAIM({
        metadata: {
          name: 'test-aim',
          namespace: null,
          uid: 'uid-123',
          labels: {},
          annotations: {
            'aim.eai.amd.com/source-registry': 'docker.io',
            'aim.eai.amd.com/source-repository': 'amdenterpriseai/test-model',
            'aim.eai.amd.com/source-tag': '1.0.0',
            'aiwb.apps.eai.amd.com/display-name': 'My imported model',
          },
          creationTimestamp: '2023-01-01T00:00:00Z',
          ownerReferences: [],
        },
      });
      const parsed = aimParser(aim);

      expect(parsed.isCustomImport).toBe(true);
    });

    it('propagates status from AIMClusterModel', () => {
      const aim = createMockAIM({
        status: {
          status: 'NotAvailable',
          imageMetadata: {
            model: {
              canonicalName: 'test/model',
              hfTokenRequired: false,
              source: 'https://example.com',
              tags: ['test'],
              title: 'Test Model',
              variants: [],
            },
            oci: {} as any,
          },
        },
      });
      const parsed = aimParser(aim);

      expect(parsed.status).toBe('NotAvailable');
    });

    it('sets status to Ready for supported models', () => {
      const aim = createMockAIM();
      const parsed = aimParser(aim);

      expect(parsed.status).toBe('Ready');
    });

    it('returns empty acceleratorTypes when discoveredProfiles is absent', () => {
      const aim = createMockAIM();
      const parsed = aimParser(aim);

      expect(parsed.acceleratorTypes).toEqual([]);
    });

    it('projects distinct accelerator types from discoveredProfiles.byHardware', () => {
      const aim = createMockAIM({
        status: {
          status: 'Ready',
          imageMetadata: {
            model: {
              canonicalName: 'test/model',
              hfTokenRequired: false,
              source: '',
              tags: [],
              title: 'Test',
              variants: [],
            },
          },
          discoveredProfiles: {
            byHardware: [
              { acceleratorType: 'gpu' },
              { acceleratorType: 'GPU' },
              { acceleratorType: 'cpu' },
            ],
          },
        },
      });
      const parsed = aimParser(aim);

      expect(parsed.acceleratorTypes).toEqual(['cpu', 'gpu']);
    });
  });

  describe('transformToAggregatedAIMs', () => {
    const createMockParsedAIM = (
      repository: string,
      version: string,
      overrides?: Partial<ParsedAIM>,
    ): ParsedAIM => ({
      model: `aim-${version}`,
      aimId: 'test/model',
      imageReference: `docker.io/${repository}:${version}`,
      annotations: {
        'aim.eai.amd.com/source-registry': 'docker.io',
        'aim.eai.amd.com/source-repository': repository,
        'aim.eai.amd.com/source-tag': version,
      },
      description: {
        short: 'Test description',
        full: 'Full test description',
      },
      title: 'Test Model',
      imageVersion: version,
      canonicalName: 'test/model',
      tags: ['test'],
      status: 'Ready',
      workloadStatuses: [AIMWorkloadStatus.NOT_DEPLOYED],
      isPreview: false,
      isHfTokenRequired: false,
      ...overrides,
    });

    it('returns empty array for undefined input', () => {
      const result = transformToAggregatedAIMs(undefined);
      expect(result).toEqual([]);
    });

    it('returns empty array for empty input', () => {
      const result = transformToAggregatedAIMs([]);
      expect(result).toEqual([]);
    });

    it('groups AIMs by repository', () => {
      const aims = [
        createMockParsedAIM('amdenterpriseai/model-a', '1.0.0'),
        createMockParsedAIM('amdenterpriseai/model-a', '2.0.0'),
        createMockParsedAIM('amdenterpriseai/model-b', '1.0.0'),
      ];

      const result = transformToAggregatedAIMs(aims);

      expect(result).toHaveLength(2);
      expect(result[0].repository).toBe('amdenterpriseai/model-a');
      expect(result[0].parsedAIMs).toHaveLength(2);
      expect(result[1].repository).toBe('amdenterpriseai/model-b');
      expect(result[1].parsedAIMs).toHaveLength(1);
    });

    it('sorts versions in descending order (latest first)', () => {
      const aims = [
        createMockParsedAIM('amdenterpriseai/model-a', '1.0.0'),
        createMockParsedAIM('amdenterpriseai/model-a', '2.0.0'),
        createMockParsedAIM('amdenterpriseai/model-a', '1.5.0'),
      ];

      const result = transformToAggregatedAIMs(aims);

      expect(result[0].parsedAIMs[0].imageVersion).toBe('2.0.0');
      expect(result[0].parsedAIMs[1].imageVersion).toBe('1.5.0');
      expect(result[0].parsedAIMs[2].imageVersion).toBe('1.0.0');
    });

    it('selects latest official release as latest (ignores preview)', () => {
      const aims = [
        createMockParsedAIM('amdenterpriseai/model-a', '2.0.0-preview', {
          isPreview: true,
        }),
        createMockParsedAIM('amdenterpriseai/model-a', '1.5.0'),
        createMockParsedAIM('amdenterpriseai/model-a', '1.0.0'),
      ];

      const result = transformToAggregatedAIMs(aims);

      expect(result[0].latestAim!.imageVersion).toBe('1.5.0');
    });

    it('latestAim is null when no official release exists (only pre-release versions)', () => {
      const aims = [
        createMockParsedAIM('amdenterpriseai/model-a', '2.0.0-preview', {
          isPreview: true,
        }),
        createMockParsedAIM('amdenterpriseai/model-a', '1.5.0-beta', {
          isPreview: true,
        }),
      ];

      const result = transformToAggregatedAIMs(aims);

      expect(result[0].latestAim).toBeNull();
    });

    it('calculates deployment counts correctly', () => {
      const aims = [
        createMockParsedAIM('amdenterpriseai/model-a', '1.0.0', {
          workloadStatuses: [AIMWorkloadStatus.DEPLOYED],
        }),
        createMockParsedAIM('amdenterpriseai/model-a', '2.0.0', {
          workloadStatuses: [
            AIMWorkloadStatus.DEPLOYED,
            AIMWorkloadStatus.PENDING,
          ],
        }),
      ];

      const result = transformToAggregatedAIMs(aims);

      expect(result[0].deploymentCounts).toEqual({
        [AIMWorkloadStatus.DEPLOYED]: 2,
        [AIMWorkloadStatus.DEGRADED]: 0,
        [AIMWorkloadStatus.PENDING]: 1,
        [AIMWorkloadStatus.STARTING]: 0,
        [AIMWorkloadStatus.FAILED]: 0,
        [AIMWorkloadStatus.NOT_DEPLOYED]: 0,
        [AIMWorkloadStatus.DELETED]: 0,
      });
    });

    it('sets isHfTokenRequired if any version requires it', () => {
      const aims = [
        createMockParsedAIM('amdenterpriseai/model-a', '1.0.0', {
          isHfTokenRequired: false,
        }),
        createMockParsedAIM('amdenterpriseai/model-a', '2.0.0', {
          isHfTokenRequired: true,
        }),
      ];

      const result = transformToAggregatedAIMs(aims);

      expect(result[0].aggregated.isHfTokenRequired).toBe(true);
    });

    it('handles version strings with build metadata', () => {
      const aims = [
        createMockParsedAIM('amdenterpriseai/model-a', '1.0.0+build.1'),
        createMockParsedAIM('amdenterpriseai/model-a', '2.0.0+build.2'),
      ];

      const result = transformToAggregatedAIMs(aims);

      expect(result[0].parsedAIMs[0].imageVersion).toBe('2.0.0+build.2');
      expect(result[0].parsedAIMs[1].imageVersion).toBe('1.0.0+build.1');
    });

    it('handles single version AIM', () => {
      const aims = [createMockParsedAIM('amdenterpriseai/model-a', '1.0.0')];

      const result = transformToAggregatedAIMs(aims);

      expect(result).toHaveLength(1);
      expect(result[0].parsedAIMs).toHaveLength(1);
      expect(result[0].latestAim!.imageVersion).toBe('1.0.0');
    });

    it('unions acceleratorTypes across versions in the same family', () => {
      const aims = [
        createMockParsedAIM('amdenterpriseai/model-a', '1.0.0', {
          acceleratorTypes: ['gpu'],
        }),
        createMockParsedAIM('amdenterpriseai/model-a', '2.0.0', {
          acceleratorTypes: ['cpu', 'gpu'],
        }),
      ];

      const result = transformToAggregatedAIMs(aims);

      expect(result[0].aggregated.acceleratorTypes).toEqual(['cpu', 'gpu']);
    });

    it('returns empty aggregated.acceleratorTypes when no version reports any', () => {
      const aims = [createMockParsedAIM('amdenterpriseai/model-a', '1.0.0')];

      const result = transformToAggregatedAIMs(aims);

      expect(result[0].aggregated.acceleratorTypes).toEqual([]);
    });

    it('extracts AI Lab name from canonical name', () => {
      const aims = [
        createMockParsedAIM('amdenterpriseai/model-a', '1.0.0', {
          canonicalName: 'meta-llama/Llama-3.1-8B',
        }),
      ];

      const result = transformToAggregatedAIMs(aims);

      expect(result[0].aggregated.aiLabName).toBe('Meta');
    });

    it('uses latest version properties for aggregated data', () => {
      const aims = [
        createMockParsedAIM('amdenterpriseai/model-a', '1.0.0', {
          title: 'Old Title',
          tags: ['old'],
        }),
        createMockParsedAIM('amdenterpriseai/model-a', '2.0.0', {
          title: 'New Title',
          tags: ['new', 'latest'],
        }),
      ];

      const result = transformToAggregatedAIMs(aims);

      expect(result[0].aggregated.title).toBe('New Title');
      expect(result[0].aggregated.tags).toEqual(['new', 'latest']);
      expect(result[0].aggregated.latestImageVersion).toBe('2.0.0');
    });

    it('handles version sorting with different lengths', () => {
      const aims = [
        createMockParsedAIM('amdenterpriseai/model-a', '1.9.0'),
        createMockParsedAIM('amdenterpriseai/model-a', '1.10.0'),
        createMockParsedAIM('amdenterpriseai/model-a', '2.0.0'),
      ];

      const result = transformToAggregatedAIMs(aims);

      expect(result[0].parsedAIMs[0].imageVersion).toBe('2.0.0');
      expect(result[0].parsedAIMs[1].imageVersion).toBe('1.10.0');
      expect(result[0].parsedAIMs[2].imageVersion).toBe('1.9.0');
    });

    it('ignores beta and rc suffixes when selecting official release', () => {
      const aims = [
        createMockParsedAIM('amdenterpriseai/model-a', '2.0.0-beta'),
        createMockParsedAIM('amdenterpriseai/model-a', '1.9.0-rc'),
        createMockParsedAIM('amdenterpriseai/model-a', '1.5.0'),
      ];

      const result = transformToAggregatedAIMs(aims);

      expect(result[0].latestAim!.imageVersion).toBe('1.5.0');
    });

    it('sets isSupported to true when at least one version is Ready', () => {
      const aims = [
        createMockParsedAIM('amdenterpriseai/model-a', '2.0.0', {
          status: 'Ready',
        }),
        createMockParsedAIM('amdenterpriseai/model-a', '1.0.0', {
          status: 'NotAvailable',
        }),
      ];

      const result = transformToAggregatedAIMs(aims);

      expect(result[0].isSupported).toBe(true);
    });

    it('latestAim is latest official READY version, null when no official READY exists', () => {
      const aims = [
        createMockParsedAIM('amdenterpriseai/model-a', '2.0.0', {
          status: 'NotAvailable',
        }),
        createMockParsedAIM('amdenterpriseai/model-a', '1.5.0', {
          status: 'Ready',
        }),
      ];

      const result = transformToAggregatedAIMs(aims);

      expect(result[0].latestAim?.imageVersion).toBe('1.5.0');
    });

    it('sets isSupported to false and latestAim to null when no version is Ready', () => {
      const aims = [
        createMockParsedAIM('amdenterpriseai/model-a', '2.0.0', {
          status: 'NotAvailable',
        }),
        createMockParsedAIM('amdenterpriseai/model-a', '1.0.0', {
          status: 'NotAvailable',
        }),
      ];

      const result = transformToAggregatedAIMs(aims);

      expect(result[0].isSupported).toBe(false);
      expect(result[0].latestAim).toBeNull();
    });

    it('sorts supported models before unsupported models', () => {
      const aims = [
        createMockParsedAIM('amdenterpriseai/unsupported', '1.0.0', {
          status: 'NotAvailable',
        }),
        createMockParsedAIM('amdenterpriseai/supported', '1.0.0', {
          status: 'Ready',
        }),
      ];

      const result = transformToAggregatedAIMs(aims);

      expect(result[0].repository).toBe('amdenterpriseai/supported');
      expect(result[0].isSupported).toBe(true);
      expect(result[1].repository).toBe('amdenterpriseai/unsupported');
      expect(result[1].isSupported).toBe(false);
    });
  });

  describe('buildFilteredCatalog', () => {
    const createMockParsedAIM = (
      repository: string,
      version: string,
      overrides?: Partial<ParsedAIM>,
    ): ParsedAIM => ({
      model: `aim-${version}`,
      aimId: 'test/model',
      imageReference: `docker.io/${repository}:${version}`,
      annotations: {
        'aim.eai.amd.com/source-registry': 'docker.io',
        'aim.eai.amd.com/source-repository': repository,
        'aim.eai.amd.com/source-tag': version,
      },
      description: { short: 'Test description', full: 'Full test description' },
      title: repository.split('/')[1] ?? repository,
      imageVersion: version,
      canonicalName: 'test/model',
      tags: ['test'],
      status: 'Ready',
      workloadStatuses: [AIMWorkloadStatus.NOT_DEPLOYED],
      isPreview: false,
      isHfTokenRequired: false,
      ...overrides,
    });

    it('preserves family support when a filter removes the only Ready version', () => {
      // The Ready version has no acceleratorTypes (won't match a CPU filter).
      // The NOT_AVAILABLE version has acceleratorTypes: ['cpu'] (matches CPU filter).
      // After filtering to CPU-only, the family should still be marked supported.
      const readyVersion = createMockParsedAIM(
        'amdenterpriseai/gated-model',
        '2.0.0',
        {
          status: 'Ready',
          acceleratorTypes: [],
          title: 'Gated Model',
        },
      );
      const cpuVersion = createMockParsedAIM(
        'amdenterpriseai/gated-model',
        '1.0.0',
        {
          status: 'NotAvailable',
          acceleratorTypes: ['cpu'],
          title: 'Gated Model',
        },
      );

      const allAims = [readyVersion, cpuVersion];
      const filteredAims = [cpuVersion]; // CPU filter removed the Ready version

      const result = buildFilteredCatalog(allAims, filteredAims);

      expect(result).toHaveLength(1);
      expect(result[0].isSupported).toBe(true);
    });

    it('places a supported-but-filtered family before an unsupported one', () => {
      // Family A: READY version excluded by filter, NOT_AVAILABLE version matches.
      // After filtering, family A appears unsupported in the raw filtered subset,
      // but buildFilteredCatalog must restore isSupported=true and sort it first.
      const familyAReady = createMockParsedAIM(
        'amdenterpriseai/family-a',
        '2.0.0',
        {
          status: 'Ready',
          acceleratorTypes: [],
          title: 'Family A',
        },
      );
      const familyACpu = createMockParsedAIM(
        'amdenterpriseai/family-a',
        '1.0.0',
        {
          status: 'NotAvailable',
          acceleratorTypes: ['cpu'],
          title: 'Family A',
        },
      );
      // Family B: genuinely unsupported, matches the filter.
      const familyBCpu = createMockParsedAIM(
        'amdenterpriseai/family-b',
        '1.0.0',
        {
          status: 'NotAvailable',
          acceleratorTypes: ['cpu'],
          title: 'Family B',
        },
      );

      const allAims = [familyAReady, familyACpu, familyBCpu];
      const filteredAims = [familyACpu, familyBCpu]; // READY version of A excluded

      const result = buildFilteredCatalog(allAims, filteredAims);

      expect(result).toHaveLength(2);
      expect(result[0].aggregated.title).toBe('Family A');
      expect(result[0].isSupported).toBe(true);
      expect(result[1].aggregated.title).toBe('Family B');
      expect(result[1].isSupported).toBe(false);
    });

    it('keeps full-catalog family order within the supported group under a filter', () => {
      // Families A, B, C are all supported in the full catalog (API order A, B, C).
      // A and C are supported only via a GPU-only Ready version; B via a CPU Ready
      // version. Under a CPU filter the inner aggregation sees A and C as
      // unsupported and B as supported, so it would emit [B, A, C]. The catalog
      // must preserve canonical order [A, B, C] regardless of the active filter.
      const aReady = createMockParsedAIM('amdenterpriseai/family-a', '2.0.0', {
        status: 'Ready',
        acceleratorTypes: ['gpu'],
        title: 'Family A',
      });
      const aCpu = createMockParsedAIM('amdenterpriseai/family-a', '1.0.0', {
        status: 'NotAvailable',
        acceleratorTypes: ['cpu'],
        title: 'Family A',
      });
      const bCpu = createMockParsedAIM('amdenterpriseai/family-b', '1.0.0', {
        status: 'Ready',
        acceleratorTypes: ['cpu'],
        title: 'Family B',
      });
      const cReady = createMockParsedAIM('amdenterpriseai/family-c', '2.0.0', {
        status: 'Ready',
        acceleratorTypes: ['gpu'],
        title: 'Family C',
      });
      const cCpu = createMockParsedAIM('amdenterpriseai/family-c', '1.0.0', {
        status: 'NotAvailable',
        acceleratorTypes: ['cpu'],
        title: 'Family C',
      });

      const allAims = [aReady, aCpu, bCpu, cReady, cCpu];
      const filteredAims = [aCpu, bCpu, cCpu]; // CPU filter

      const result = buildFilteredCatalog(allAims, filteredAims);

      expect(result.map((r) => r.aggregated.title)).toEqual([
        'Family A',
        'Family B',
        'Family C',
      ]);
      expect(result.every((r) => r.isSupported)).toBe(true);
    });

    it('preserves deployment counts when a filter hides the deployed version', () => {
      // The deployed version is GPU-only; the CPU filter hides it. The family must
      // still report its deployment so the "Has deployments" badge keeps showing.
      const deployedGpu = createMockParsedAIM(
        'amdenterpriseai/deployed-model',
        '2.0.0',
        {
          status: 'Ready',
          acceleratorTypes: ['gpu'],
          workloadStatuses: [AIMWorkloadStatus.DEPLOYED],
          title: 'Deployed Model',
        },
      );
      const cpuVersion = createMockParsedAIM(
        'amdenterpriseai/deployed-model',
        '1.0.0',
        {
          status: 'NotAvailable',
          acceleratorTypes: ['cpu'],
          workloadStatuses: [AIMWorkloadStatus.NOT_DEPLOYED],
          title: 'Deployed Model',
        },
      );

      const allAims = [deployedGpu, cpuVersion];
      const filteredAims = [cpuVersion]; // CPU filter hid the deployed GPU version

      const result = buildFilteredCatalog(allAims, filteredAims);

      expect(result).toHaveLength(1);
      expect(
        result[0].deploymentCounts[AIMWorkloadStatus.DEPLOYED],
      ).toBeGreaterThan(0);
    });

    it('sorts supported families before unsupported', () => {
      const supported = createMockParsedAIM('amdenterpriseai/zebra', '1.0.0', {
        status: 'Ready',
        title: 'Zebra Model',
      });
      const unsupported = createMockParsedAIM(
        'amdenterpriseai/alpha',
        '1.0.0',
        {
          status: 'NotAvailable',
          title: 'Alpha Model',
        },
      );

      const aims = [unsupported, supported];
      const result = buildFilteredCatalog(aims, aims);

      expect(result[0].aggregated.title).toBe('Zebra Model');
      expect(result[0].isSupported).toBe(true);
      expect(result[1].aggregated.title).toBe('Alpha Model');
      expect(result[1].isSupported).toBe(false);
    });
  });
});
