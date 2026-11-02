// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { vi } from 'vitest';

import type { DeployAIMFormValues } from '@/components/features/models/DeployAIMWizard/types';
import {
  AIM_PROFILE_TYPE_OPTIMIZED,
  AIMWorkloadStatus,
  type AIMClusterProfile,
  type ParsedAIM,
} from '@/types/aims';

vi.mock('next-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

export const formValues: DeployAIMFormValues = {
  model: 'test-model',
  performanceMode: 'latency',
  autoscalingEnabled: false,
};

export const createMockProfile = (
  overrides: Partial<AIMClusterProfile['spec']> = {},
  name = 'profile-latency',
): AIMClusterProfile => ({
  metadata: { name, labels: {} },
  spec: {
    aimId: 'test-model',
    type: AIM_PROFILE_TYPE_OPTIMIZED,
    acceleratorModel: 'MI300X',
    acceleratorCount: 8,
    metric: 'latency',
    precision: 'fp8',
    ...overrides,
  },
  status: { status: 'Ready' },
});

export const createMockParsedAIM = (
  overrides: Partial<ParsedAIM> = {},
): ParsedAIM => ({
  model: 'aim-test-model',
  aimId: 'org/test-model',
  imageReference: 'img:1.2.0',
  annotations: {},
  description: { short: '', full: '' },
  title: 'Test Model',
  imageVersion: '1.2.0',
  canonicalName: 'org/test-model',
  tags: [],
  status: 'Ready',
  workloadStatuses: [AIMWorkloadStatus.NOT_DEPLOYED],
  isPreview: false,
  isHfTokenRequired: false,
  ...overrides,
});
