// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { AIMWorkloadStatus, ParsedAIM, AggregatedAIM } from '@/types/aims';

export const mockAims: ParsedAIM[] = [
  {
    description: {
      short: 'A large language model for text generation',
      full: 'Llama 2 is a family of large language models that use an optimized transformer architecture.',
    },
    title: 'Llama 2 7B',
    imageVersion: '2.0.1',
    canonicalName: 'meta-llama/llama-2-7b',
    tags: ['llm', 'text-generation', 'chat'],
    status: 'Ready',
    workloadStatuses: [AIMWorkloadStatus.DEPLOYED],
    isPreview: false,
    isHfTokenRequired: true,
    model: 'aim-llama-2-7b-v2',
    aimId: 'aim-llama-2-7b-v2',
    annotations: {
      'aim.eai.amd.com/source-registry': 'docker.io',
      'aim.eai.amd.com/source-repository':
        'amdenterpriseai/aim-meta-llama-llama-2-7b',
      'aim.eai.amd.com/source-tag': '2.0.1',
    },
    imageReference: 'docker.io/amdenterpriseai/aim-meta-llama-llama-2-7b:2.0.1',
    deployedService: {
      id: 'service-1',
      metadata: {
        name: 'llama-2-7b-service',
        namespace: 'test-namespace',
        uid: 'uid-1',
        labels: {},
        annotations: {},
        creationTimestamp: '2023-01-01T00:00:00Z',
        ownerReferences: [],
      },
      spec: {
        model: {
          name: 'aim-llama-2-7b-v2',
        },
        replicas: 1,
        routing: {
          annotations: {},
          enabled: true,
        },
        runtimeConfigName: 'default-runtime',
        profile: { name: 'mock-profile', selector: { metric: 'latency' } },
      },
      status: {
        status: 'Running',
        routing: {
          path: '/test-namespace/service-1',
        },
      },
      statusValue: '',
      endpoints: {
        internal: 'http://llama-2-7b-service.test-namespace.svc.cluster.local',
        external: 'https://api.example.com/test-namespace/service-1',
      },
    },
    deployedServices: [
      {
        id: 'service-1',
        metadata: {
          name: 'llama-2-7b-service',
          namespace: 'test-namespace',
          uid: 'uid-1',
          labels: {},
          annotations: {},
          creationTimestamp: '2023-01-01T00:00:00Z',
          ownerReferences: [],
        },
        spec: {
          model: {
            name: 'aim-llama-2-7b-v2',
          },
          replicas: 1,
          routing: {
            annotations: {},
            enabled: true,
          },
          runtimeConfigName: 'default-runtime',
          profile: { name: 'mock-profile', selector: { metric: 'latency' } },
        },
        status: {
          status: 'Running',
          routing: {
            path: '/test-namespace/service-1',
          },
        },
        statusValue: '',
        endpoints: {
          internal:
            'http://llama-2-7b-service.test-namespace.svc.cluster.local',
          external: 'https://api.example.com/test-namespace/service-1',
        },
      },
    ],
  },
  {
    description: {
      short: 'A large language model for text generation',
      full: 'Llama 2 is a family of large language models that use an optimized transformer architecture.',
    },
    title: 'Llama 2 7B',
    imageVersion: '1.5.0',
    canonicalName: 'meta-llama/llama-2-7b',
    tags: ['llm', 'text-generation', 'chat'],
    status: 'Ready',
    workloadStatuses: [],
    isPreview: false,
    isHfTokenRequired: true,
    model: 'aim-llama-2-7b-v1',
    aimId: 'aim-llama-2-7b-v1',
    annotations: {
      'aim.eai.amd.com/source-registry': 'docker.io',
      'aim.eai.amd.com/source-repository':
        'amdenterpriseai/aim-meta-llama-llama-2-7b',
      'aim.eai.amd.com/source-tag': '1.5.0',
    },
    imageReference: 'docker.io/amdenterpriseai/aim-meta-llama-llama-2-7b:1.5.0',
    deployedServices: [],
  },
  {
    description: {
      short: 'Text to image generation model',
      full: 'Stable Diffusion XL is a powerful text-to-image model.',
    },
    title: 'Stable Diffusion XL',
    imageVersion: '1.0.0',
    canonicalName: 'stabilityai/stable-diffusion-xl',
    tags: ['image-generation', 'diffusion'],
    status: 'Ready',
    workloadStatuses: [],
    isPreview: false,
    isHfTokenRequired: false,
    model: 'aim-stable-diffusion-xl',
    aimId: 'aim-stable-diffusion-xl',
    annotations: {
      'aim.eai.amd.com/source-registry': 'docker.io',
      'aim.eai.amd.com/source-repository':
        'amdenterpriseai/aim-stabilityai-stable-diffusion-xl',
      'aim.eai.amd.com/source-tag': '1.0.0',
    },
    imageReference:
      'docker.io/amdenterpriseai/aim-stabilityai-stable-diffusion-xl:1.0.0',
    deployedServices: [],
  },
  {
    description: {
      short: 'Object detection model',
      full: 'A vision model for detecting objects in images.',
    },
    title: 'Vision Detection Model',
    imageVersion: '2.0.0-preview',
    canonicalName: 'detection-model',
    tags: ['vision', 'object-detection'],
    status: 'Ready',
    workloadStatuses: [AIMWorkloadStatus.PENDING],
    isPreview: true,
    isHfTokenRequired: false,
    model: 'aim-detection-model',
    aimId: 'aim-detection-model',
    annotations: {
      'aim.eai.amd.com/source-registry': 'docker.io',
      'aim.eai.amd.com/source-repository':
        'amdenterpriseai/aim-detection-model',
      'aim.eai.amd.com/source-tag': '2.0.0-preview',
    },
    imageReference:
      'docker.io/amdenterpriseai/aim-detection-model:2.0.0-preview',
    deployedService: {
      id: 'service-3',
      metadata: {
        name: 'detection-model-service',
        namespace: 'test-namespace',
        uid: 'uid-3',
        labels: {},
        annotations: {},
        creationTimestamp: '2023-01-03T00:00:00Z',
        ownerReferences: [],
      },
      spec: {
        model: {
          name: 'aim-detection-model',
        },
        replicas: 1,
        routing: {
          annotations: {},
          enabled: true,
        },
        runtimeConfigName: 'default-runtime',
        profile: { name: 'mock-profile' },
      },
      status: {
        status: 'Pending',
      },
      statusValue: '',
      endpoints: {
        internal: '',
        external: '',
      },
    },
    deployedServices: [
      {
        id: 'service-3',
        metadata: {
          name: 'detection-model-service',
          namespace: 'test-namespace',
          uid: 'uid-3',
          labels: {},
          annotations: {},
          creationTimestamp: '2023-01-03T00:00:00Z',
          ownerReferences: [],
        },
        spec: {
          model: {
            name: 'aim-detection-model',
          },
          replicas: 1,
          routing: {
            annotations: {},
            enabled: true,
          },
          runtimeConfigName: 'default-runtime',
          profile: { name: 'mock-profile' },
        },
        status: {
          status: 'Pending',
        },
        statusValue: '',
        endpoints: {
          internal: '',
          external: '',
        },
      },
    ],
  },
];

// Aggregated AIM with multiple versions and deployments
const mockLlamaParsedAims: ParsedAIM[] = [
  { ...mockAims[0], isLatest: true },
  { ...mockAims[1], isLatest: false },
];
export const mockAggregatedAims: AggregatedAIM[] = [
  {
    repository: 'amdenterpriseai/aim-meta-llama-llama-2-7b',
    parsedAIMs: mockLlamaParsedAims,
    latestAim: mockLlamaParsedAims[0]!,
    isSupported: true,
    deploymentCounts: {
      [AIMWorkloadStatus.DEPLOYED]: 1,
      [AIMWorkloadStatus.DEGRADED]: 0,
      [AIMWorkloadStatus.PENDING]: 0,
      [AIMWorkloadStatus.STARTING]: 0,
      [AIMWorkloadStatus.FAILED]: 0,
      [AIMWorkloadStatus.NOT_DEPLOYED]: 0,
      [AIMWorkloadStatus.DELETED]: 0,
    },
    aggregated: {
      title: 'Llama 2 7B',
      aiLabName: 'Meta',
      canonicalName: 'meta-llama/llama-2-7b',
      latestImageVersion: '2.0.1',
      isHfTokenRequired: true,
      tags: ['llm', 'text-generation', 'chat'],
      description: {
        short: 'A large language model for text generation',
        full: 'Llama 2 is a family of large language models that use an optimized transformer architecture.',
      },
    },
  },
  (() => {
    const sdParsedAims = [{ ...mockAims[2], isLatest: true }];
    return {
      repository: 'amdenterpriseai/aim-stabilityai-stable-diffusion-xl',
      parsedAIMs: sdParsedAims,
      latestAim: sdParsedAims[0],
      isSupported: true,
      deploymentCounts: {
        [AIMWorkloadStatus.DEPLOYED]: 0,
        [AIMWorkloadStatus.DEGRADED]: 0,
        [AIMWorkloadStatus.PENDING]: 0,
        [AIMWorkloadStatus.STARTING]: 0,
        [AIMWorkloadStatus.FAILED]: 0,
        [AIMWorkloadStatus.NOT_DEPLOYED]: 0,
        [AIMWorkloadStatus.DELETED]: 0,
      },
      aggregated: {
        title: 'Stable Diffusion XL',
        aiLabName: 'stabilityai',
        canonicalName: 'stabilityai/stable-diffusion-xl',
        latestImageVersion: '1.0.0',
        isHfTokenRequired: false,
        tags: ['image-generation', 'diffusion'],
        description: {
          short: 'Text to image generation model',
          full: 'Stable Diffusion XL is a powerful text-to-image model.',
        },
      },
    };
  })(),
  (() => {
    const detectionParsedAims = [{ ...mockAims[3], isLatest: true }];
    return {
      repository: 'amdenterpriseai/aim-detection-model',
      parsedAIMs: detectionParsedAims,
      latestAim: detectionParsedAims[0],
      isSupported: true,
      deploymentCounts: {
        [AIMWorkloadStatus.DEPLOYED]: 0,
        [AIMWorkloadStatus.DEGRADED]: 0,
        [AIMWorkloadStatus.PENDING]: 1,
        [AIMWorkloadStatus.STARTING]: 0,
        [AIMWorkloadStatus.FAILED]: 0,
        [AIMWorkloadStatus.NOT_DEPLOYED]: 0,
        [AIMWorkloadStatus.DELETED]: 0,
      },
      aggregated: {
        title: 'Vision Detection Model',
        aiLabName: 'detection-model',
        canonicalName: 'detection-model',
        latestImageVersion: '2.0.0-preview',
        isHfTokenRequired: false,
        tags: ['vision', 'object-detection'],
        description: {
          short: 'Object detection model',
          full: 'A vision model for detecting objects in images.',
        },
      },
    };
  })(),
];

// Mock with multiple deployments of the same model
const mockMultiDeployParsedAims: ParsedAIM[] = [
  {
    ...mockAims[0],
    deployedServices: [
      {
        id: 'service-1',
        metadata: {
          name: 'llama-deployment-1',
          namespace: 'test-namespace',
          uid: 'uid-1',
          labels: {},
          annotations: {},
          creationTimestamp: '2023-01-01T00:00:00Z',
          ownerReferences: [],
        },
        spec: {
          model: {
            name: 'aim-llama-2-7b-v2',
          },
          replicas: 1,
          routing: {
            annotations: {},
            enabled: true,
          },
          runtimeConfigName: 'default-runtime',
          profile: { name: 'mock-profile', selector: { metric: 'latency' } },
        },
        status: {
          status: 'Running',
          routing: {
            path: '/test-namespace/service-1',
          },
        },
        statusValue: '',
        endpoints: {
          internal:
            'http://llama-deployment-1.test-namespace.svc.cluster.local',
          external: 'https://api.example.com/test-namespace/service-1',
        },
      },
      {
        id: 'service-2',
        metadata: {
          name: 'llama-deployment-2',
          namespace: 'test-namespace',
          uid: 'uid-2',
          labels: {},
          annotations: {},
          creationTimestamp: '2023-01-02T00:00:00Z',
          ownerReferences: [],
        },
        spec: {
          model: {
            name: 'aim-llama-2-7b-v2',
          },
          replicas: 1,
          routing: {
            annotations: {},
            enabled: true,
          },
          runtimeConfigName: 'default-runtime',
          profile: { name: 'mock-profile', selector: { metric: 'throughput' } },
        },
        status: {
          status: 'Pending',
          routing: {
            path: '/test-namespace/service-2',
          },
        },
        statusValue: '',
        endpoints: {
          internal:
            'http://llama-deployment-2.test-namespace.svc.cluster.local',
          external: 'https://api.example.com/test-namespace/service-2',
        },
      },
    ],
    workloadStatuses: [AIMWorkloadStatus.DEPLOYED, AIMWorkloadStatus.PENDING],
    isLatest: true,
  },
];
export const mockAggregatedAimWithMultipleDeployments: AggregatedAIM = {
  repository: 'amdenterpriseai/aim-meta-llama-llama-2-7b',
  isSupported: true,
  parsedAIMs: mockMultiDeployParsedAims,
  latestAim: mockMultiDeployParsedAims[0],
  deploymentCounts: {
    [AIMWorkloadStatus.DEPLOYED]: 1,
    [AIMWorkloadStatus.DEGRADED]: 0,
    [AIMWorkloadStatus.PENDING]: 1,
    [AIMWorkloadStatus.STARTING]: 0,
    [AIMWorkloadStatus.FAILED]: 0,
    [AIMWorkloadStatus.NOT_DEPLOYED]: 0,
    [AIMWorkloadStatus.DELETED]: 0,
  },
  aggregated: {
    title: 'Llama 2 7B',
    aiLabName: 'Meta',
    canonicalName: 'meta-llama/llama-2-7b',
    latestImageVersion: '2.0.1',
    isHfTokenRequired: true,
    tags: ['llm', 'text-generation', 'chat'],
    description: {
      short: 'A large language model for text generation',
      full: 'Llama 2 is a family of large language models that use an optimized transformer architecture.',
    },
  },
};

const mockUnsupportedParsedAims = [
  {
    description: {
      short: 'An unsupported model',
      full: 'This model is not compatible with current cluster hardware.',
    },
    title: 'Unsupported Model',
    imageVersion: '1.0.0',
    canonicalName: 'unsupported/model',
    tags: ['llm'],
    status: 'NotAvailable',
    workloadStatuses: [AIMWorkloadStatus.NOT_DEPLOYED],
    isPreview: false,
    isHfTokenRequired: false,
    model: 'aim-unsupported-model',
    aimId: 'aim-unsupported-model',
    annotations: {
      'aim.eai.amd.com/source-registry': 'docker.io',
      'aim.eai.amd.com/source-repository':
        'amdenterpriseai/aim-unsupported-model',
      'aim.eai.amd.com/source-tag': '1.0.0',
    },
    imageReference: 'docker.io/amdenterpriseai/aim-unsupported-model:1.0.0',
    deployedServices: [],
    isLatest: true,
  },
];
export const mockUnsupportedAggregatedAim: AggregatedAIM = {
  repository: 'amdenterpriseai/aim-unsupported-model',
  isSupported: false,
  parsedAIMs: mockUnsupportedParsedAims,
  latestAim: null,
  deploymentCounts: {
    [AIMWorkloadStatus.DEPLOYED]: 0,
    [AIMWorkloadStatus.DEGRADED]: 0,
    [AIMWorkloadStatus.PENDING]: 0,
    [AIMWorkloadStatus.STARTING]: 0,
    [AIMWorkloadStatus.FAILED]: 0,
    [AIMWorkloadStatus.NOT_DEPLOYED]: 0,
    [AIMWorkloadStatus.DELETED]: 0,
  },
  aggregated: {
    title: 'Unsupported Model',
    aiLabName: 'unsupported',
    canonicalName: 'unsupported/model',
    latestImageVersion: '1.0.0',
    isHfTokenRequired: false,
    tags: ['llm'],
    description: {
      short: 'An unsupported model',
      full: 'This model is not compatible with current cluster hardware.',
    },
  },
};

const mockMixedSupportParsedAims = [
  {
    description: {
      short: 'A mixed support model',
      full: 'Some versions of this model are supported, others are not.',
    },
    title: 'Mixed Support Model',
    imageVersion: '2.0.0',
    canonicalName: 'mixed/model',
    tags: ['llm'],
    status: 'Ready',
    workloadStatuses: [AIMWorkloadStatus.NOT_DEPLOYED],
    isPreview: false,
    isHfTokenRequired: false,
    model: 'aim-mixed-v2',
    aimId: 'aim-mixed-v2',
    annotations: {
      'aim.eai.amd.com/source-registry': 'docker.io',
      'aim.eai.amd.com/source-repository':
        'amdenterpriseai/aim-mixed-support-model',
      'aim.eai.amd.com/source-tag': '2.0.0',
    },
    imageReference: 'docker.io/amdenterpriseai/aim-mixed-support-model:2.0.0',
    deployedServices: [],
    isLatest: true,
  },
  {
    description: {
      short: 'A mixed support model',
      full: 'Some versions of this model are supported, others are not.',
    },
    title: 'Mixed Support Model',
    imageVersion: '1.0.0',
    canonicalName: 'mixed/model',
    tags: ['llm'],
    status: 'NotAvailable',
    workloadStatuses: [AIMWorkloadStatus.NOT_DEPLOYED],
    isPreview: false,
    isHfTokenRequired: false,
    model: 'aim-mixed-v1',
    aimId: 'aim-mixed-v1',
    annotations: {
      'aim.eai.amd.com/source-registry': 'docker.io',
      'aim.eai.amd.com/source-repository':
        'amdenterpriseai/aim-mixed-support-model',
      'aim.eai.amd.com/source-tag': '1.0.0',
    },
    imageReference: 'docker.io/amdenterpriseai/aim-mixed-support-model:1.0.0',
    deployedServices: [],
    isLatest: false,
  },
];
export const mockMixedSupportAggregatedAim: AggregatedAIM = {
  repository: 'amdenterpriseai/aim-mixed-support-model',
  isSupported: true,
  parsedAIMs: mockMixedSupportParsedAims,
  latestAim: mockMixedSupportParsedAims[0],
  deploymentCounts: {
    [AIMWorkloadStatus.DEPLOYED]: 0,
    [AIMWorkloadStatus.DEGRADED]: 0,
    [AIMWorkloadStatus.PENDING]: 0,
    [AIMWorkloadStatus.STARTING]: 0,
    [AIMWorkloadStatus.FAILED]: 0,
    [AIMWorkloadStatus.NOT_DEPLOYED]: 0,
    [AIMWorkloadStatus.DELETED]: 0,
  },
  aggregated: {
    title: 'Mixed Support Model',
    aiLabName: 'mixed',
    canonicalName: 'mixed/model',
    latestImageVersion: '2.0.0',
    isHfTokenRequired: false,
    tags: ['llm'],
    description: {
      short: 'A mixed support model',
      full: 'Some versions of this model are supported, others are not.',
    },
  },
};

const mockStartingParsedAims: ParsedAIM[] = [
  {
    description: {
      short: 'A starting model deployment',
      full: 'This model is currently starting up.',
    },
    title: 'Starting Model',
    imageVersion: '1.0.0',
    canonicalName: 'test/starting-model',
    tags: ['llm'],
    status: 'Ready',
    workloadStatuses: [AIMWorkloadStatus.STARTING],
    isPreview: false,
    isHfTokenRequired: false,
    model: 'aim-starting-model',
    aimId: 'aim-starting-model',
    annotations: {
      'aim.eai.amd.com/source-registry': 'docker.io',
      'aim.eai.amd.com/source-repository': 'amdenterpriseai/aim-starting-model',
      'aim.eai.amd.com/source-tag': '1.0.0',
    },
    imageReference: 'docker.io/amdenterpriseai/aim-starting-model:1.0.0',
    deployedService: {
      id: 'service-starting',
      metadata: {
        name: 'starting-model-service',
        namespace: 'test-namespace',
        uid: 'uid-starting',
        labels: {},
        annotations: {},
        creationTimestamp: '2023-01-04T00:00:00Z',
        ownerReferences: [],
      },
      spec: {
        model: {
          name: 'aim-starting-model',
        },
        replicas: 1,
        routing: {
          annotations: {},
          enabled: true,
        },
        runtimeConfigName: 'default-runtime',
        profile: { name: 'mock-profile' },
      },
      status: {
        status: 'Starting',
      },
      statusValue: '',
      endpoints: {
        internal: '',
        external: '',
      },
    },
    deployedServices: [
      {
        id: 'service-starting',
        metadata: {
          name: 'starting-model-service',
          namespace: 'test-namespace',
          uid: 'uid-starting',
          labels: {},
          annotations: {},
          creationTimestamp: '2023-01-04T00:00:00Z',
          ownerReferences: [],
        },
        spec: {
          model: {
            name: 'aim-starting-model',
          },
          replicas: 1,
          routing: {
            annotations: {},
            enabled: true,
          },
          runtimeConfigName: 'default-runtime',
          profile: { name: 'mock-profile' },
        },
        status: {
          status: 'Starting',
        },
        statusValue: '',
        endpoints: {
          internal: '',
          external: '',
        },
      },
    ],
    isLatest: true,
  },
];
export const mockAggregatedAimWithStarting: AggregatedAIM = {
  repository: 'amdenterpriseai/aim-starting-model',
  isSupported: true,
  parsedAIMs: mockStartingParsedAims,
  latestAim: mockStartingParsedAims[0],
  deploymentCounts: {
    [AIMWorkloadStatus.DEPLOYED]: 0,
    [AIMWorkloadStatus.DEGRADED]: 0,
    [AIMWorkloadStatus.PENDING]: 0,
    [AIMWorkloadStatus.STARTING]: 1,
    [AIMWorkloadStatus.FAILED]: 0,
    [AIMWorkloadStatus.NOT_DEPLOYED]: 0,
    [AIMWorkloadStatus.DELETED]: 0,
  },
  aggregated: {
    title: 'Starting Model',
    aiLabName: 'test',
    canonicalName: 'test/starting-model',
    latestImageVersion: '1.0.0',
    isHfTokenRequired: false,
    tags: ['llm'],
    description: {
      short: 'A starting model deployment',
      full: 'This model is currently starting up.',
    },
  },
};
