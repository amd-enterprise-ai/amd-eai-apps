// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { components } from '@/types/api';

type ApiKeyResponse = components['schemas']['ApiKeyResponse'];
type ApiKeyWithFullKey = components['schemas']['ApiKeyWithFullKey'];

export const generateMockApiKeys = (count: number): ApiKeyResponse[] => {
  return Array.from({ length: count }, (_, i) => ({
    id: `api-key-${i + 1}`,
    displayName: `API Key ${i + 1}`,
    truncatedKey: `sk_test_••••••••••••${(i + 1).toString().padStart(4, '0')}`,
    createdAt: new Date(2024, 0, i + 1).toISOString(),
    updatedAt: new Date(2024, 0, i + 1).toISOString(),
    createdBy: `user${i + 1}@example.com`,
    updatedBy: `user${i + 1}@example.com`,
    namespace: 'project-1',
  }));
};

export const generateMockApiKey = (
  overrides?: Partial<ApiKeyResponse>,
): ApiKeyResponse => ({
  id: 'api-key-1',
  displayName: 'Test API Key',
  truncatedKey: 'sk_test_••••••••••••1234',
  createdAt: '2024-01-01T00:00:00Z',
  updatedAt: '2024-01-01T00:00:00Z',
  createdBy: 'test@example.com',
  updatedBy: 'test@example.com',
  namespace: 'project-1',
  ...overrides,
});

export const generateMockApiKeyResponse = () => ({
  data: generateMockApiKeys(3),
});

export const generateMockCreateApiKeyData = () => ({
  displayName: 'New API Key',
});

export const generateMockFullApiKey = (
  overrides?: Partial<ApiKeyWithFullKey>,
): ApiKeyWithFullKey => ({
  id: 'api-key-new',
  displayName: 'New API Key',
  truncatedKey: 'sk_live_••••••••••••7890',
  createdAt: '2024-01-01T00:00:00Z',
  updatedAt: '2024-01-01T00:00:00Z',
  createdBy: 'test@example.com',
  updatedBy: 'test@example.com',
  namespace: 'project-1',
  ttl: null,
  fullKey: 'sk_live_abcdef1234567890abcdef1234567890',
  ...overrides,
});
