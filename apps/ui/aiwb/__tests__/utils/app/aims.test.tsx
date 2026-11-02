// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { aimParser } from '@/lib/app/aims';
import {
  AIMWorkloadStatus,
  AIMServiceStatus,
  AIMClusterModel,
  AIMService,
} from '@/types/aims';

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
        title: 'Test AIM',
        variants: [],
      },
      oci: {
        description: 'Short description',
        version: '1.0.0',
        title: 'Test AIM',
        licenses: 'MIT',
        vendor: 'Test Vendor',
        source: 'https://github.com/example/model',
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
    model: { name: 'test-aim' },
    replicas: 1,
    routing: { annotations: {}, enabled: true },
    runtimeConfigName: 'default',
  },
  status: { status },
  statusValue: '',
  endpoints: {
    internal: 'http://test-service.test-namespace.svc.cluster.local',
    external: 'https://api.example.com/test-namespace/service-123',
  },
});

describe('aims utils', () => {
  describe('aimParser', () => {
    it('parses aim fields correctly', () => {
      const aim = createMockAIM();
      const result = aimParser(aim);

      expect(result.title).toBe('Test AIM');
      expect(result.description.short).toBe('Short description');
      expect(result.description.full).toBe('Full description');
      expect(result.canonicalName).toBe('test/model');
      expect(result.isPreview).toBe(false);
      expect(result.isHfTokenRequired).toBe(false);
    });

    it('detects preview versions via tags', () => {
      const aim = createMockAIM({
        status: {
          status: 'Ready' as any,
          imageMetadata: {
            model: {
              canonicalName: 'test/model',
              hfTokenRequired: false,
              source: 'https://example.com',
              tags: ['test', 'preview'],
              title: 'Test AIM',
              variants: [],
            },
            oci: {} as any,
          },
        },
      });

      expect(aimParser(aim).isPreview).toBe(true);
    });

    it('non-preview tags do not mark as preview', () => {
      const aim = createMockAIM();
      expect(aimParser(aim).isPreview).toBe(false);
    });

    it('determines workload status from deployed services', () => {
      const aim = createMockAIM();

      expect(aimParser(aim).workloadStatuses).toEqual([
        AIMWorkloadStatus.NOT_DEPLOYED,
      ]);
      expect(
        aimParser(aim, [createMockService('Running')]).workloadStatuses,
      ).toContain(AIMWorkloadStatus.DEPLOYED);
      expect(
        aimParser(aim, [createMockService('Pending')]).workloadStatuses,
      ).toContain(AIMWorkloadStatus.PENDING);
      expect(
        aimParser(aim, [createMockService('Failed')]).workloadStatuses,
      ).toContain(AIMWorkloadStatus.FAILED);
      expect(
        aimParser(aim, [createMockService('Degraded')]).workloadStatuses,
      ).toContain(AIMWorkloadStatus.DEGRADED);
    });

    it('parses hfTokenRequired correctly', () => {
      const aimRequired = createMockAIM({
        status: {
          status: 'Ready' as any,
          imageMetadata: {
            model: {
              canonicalName: 'test/model',
              hfTokenRequired: true,
              source: 'https://example.com',
              tags: [],
              title: 'Test AIM',
              variants: [],
            },
            oci: {} as any,
          },
        },
      });
      const aimNotRequired = createMockAIM();

      expect(aimParser(aimRequired).isHfTokenRequired).toBe(true);
      expect(aimParser(aimNotRequired).isHfTokenRequired).toBe(false);
    });

    it('handles empty deployedServices array', () => {
      const aim = createMockAIM();
      const result = aimParser(aim, []);

      expect(result.workloadStatuses).toEqual([AIMWorkloadStatus.NOT_DEPLOYED]);
      expect(result.deployedServices).toEqual([]);
    });

    it('handles multiple deployed services', () => {
      const aim = createMockAIM();
      const services = [
        createMockService('Running'),
        createMockService('Pending'),
      ];
      const result = aimParser(aim, services);

      expect(result.workloadStatuses).toEqual([
        AIMWorkloadStatus.DEPLOYED,
        AIMWorkloadStatus.PENDING,
      ]);
      expect(result.deployedServices).toEqual(services);
    });
  });
});
