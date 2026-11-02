// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  act,
  render,
  screen,
  fireEvent,
  waitFor,
} from '@testing-library/react';

import {
  fetchApiKeyDetails,
  fetchApiKeyMetrics,
  deleteApiKey,
} from '@/lib/app/api-keys';
import { listAllInferenceDeployments } from '@/lib/app/inference';
import { generateMockApiKey } from '@/__mocks__/utils/api-keys-mock';
import type { components } from '@/types/api';
import type { AIMService } from '@/types/aims';

type ApiKeyMetricsResponse = components['schemas']['ApiKeyMetricsResponse'];

import ApiKeyMetricsDashboard, {
  computeFilteredStats,
} from '@/components/features/api-keys/ApiKeyMetricsDashboard';
import wrapper from '@/__tests__/ProviderWrapper';

vi.mock('@/lib/app/api-keys', () => ({
  fetchApiKeyDetails: vi.fn(),
  fetchApiKeyMetrics: vi.fn(),
  deleteApiKey: vi.fn(),
}));

vi.mock('@/lib/app/inference', () => ({
  listAllInferenceDeployments: vi.fn(),
  getInferenceModel: vi.fn().mockResolvedValue(null),
}));

vi.mock('@/lib/app/models', () => ({
  listAllProjectFineTunedModels: vi.fn().mockResolvedValue([]),
}));

vi.mock('@/lib/app/aims', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/app/aims')>();
  return {
    ...actual,
    getAimClusterProfilesByAimIds: vi.fn().mockResolvedValue([]),
    getProjectAimProfilesByAimIds: vi.fn().mockResolvedValue([]),
    getAimClusterProfileByName: vi.fn().mockResolvedValue({
      metadata: { name: 'cluster-profile' },
      spec: {},
    }),
  };
});

vi.mock('next/router', () => ({
  useRouter: () => ({
    push: vi.fn(),
  }),
}));

vi.mock('@/contexts/ProjectContext', () => ({
  useProject: () => ({ projectPath: (path: string) => `/project-1${path}` }),
}));

// Mock react-aria collection components that don't render correctly in JSDOM
vi.mock('@amdenterpriseai/components', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@amdenterpriseai/components')>();
  return {
    ...actual,
    Tabs: ({
      children,
      onSelectionChange,
      selectedKey,
      defaultSelectedKey,
    }: any) => (
      <div
        data-testid="tabs"
        data-selected-key={selectedKey ?? defaultSelectedKey}
      >
        {children}
      </div>
    ),
    Tab: ({ key: tabKey, title, children }: any) => (
      <div data-testid={`tab-${tabKey}`} data-title={title}>
        {children}
      </div>
    ),
    Select: ({
      children,
      onSelectionChange,
      selectedKeys,
      'aria-label': ariaLabel,
      placeholder,
      items,
    }: any) => (
      <select
        aria-label={ariaLabel}
        value={
          selectedKeys ? (Array.from(selectedKeys)[0] as string) : undefined
        }
        onChange={(e) => onSelectionChange?.(new Set([e.target.value]))}
      >
        {items?.map((item: any) => (
          <option key={item.key} value={item.key}>
            {typeof children === 'function' ? item.key : item.key}
          </option>
        ))}
        {typeof children !== 'function' && children}
      </select>
    ),
    SelectItem: ({ children, value }: any) => (
      <option value={value}>{children}</option>
    ),
  };
});

const mockFetchApiKeyDetails = vi.mocked(fetchApiKeyDetails);
const mockFetchApiKeyMetrics = vi.mocked(fetchApiKeyMetrics);
const mockDeleteApiKey = vi.mocked(deleteApiKey);
const mockListAllInferenceDeployments = vi.mocked(listAllInferenceDeployments);

// aim_service_id format in Prometheus: {namespace}-{inferenceServiceName}
// inferenceServiceName is derived from the internal endpoint before "-predictor"
const mockDeployment = (name: string): AIMService => ({
  id: name,
  metadata: {
    name,
    namespace: 'project-1',
    uid: name,
    labels: {},
    annotations: { 'airm.silogen.ai/submitter': 'test-user' },
    creationTimestamp: '2024-01-01T00:00:00Z',
    ownerReferences: [],
  },
  spec: {
    model: { name },
    replicas: 1,
    runtimeConfigName: '',
  } as AIMService['spec'],
  status: {
    status: 'Running',
    resolvedProfile: { name: 'cluster-profile', scope: 'Cluster' },
    runtime: { currentReplicas: 1, desiredReplicas: 1 },
  },
  statusValue: '',
  endpoints: {
    internal: `http://${name}-predictor.project-1.svc.cluster.local`,
  },
});

const mockMetrics: ApiKeyMetricsResponse = {
  stats: {
    totalRequests: 1500,
    successfulRequests: 1400,
    failedRequests: 100,
    totalTokens: 250000,
    linkedDeployments: 2,
  },
  services: ['project-1-service-a', 'project-1-service-b'],
  requestsOverTime: {
    total: [
      {
        date: '2024-01-01T00:00:00Z',
        'project-1-service-a': 10,
        'project-1-service-b': 5,
      },
    ],
    successful: [
      {
        date: '2024-01-01T00:00:00Z',
        'project-1-service-a': 9,
        'project-1-service-b': 5,
      },
    ],
    failed: [
      {
        date: '2024-01-01T00:00:00Z',
        'project-1-service-a': 1,
        'project-1-service-b': 0,
      },
    ],
  },
  tokensOverTime: {
    total: [
      {
        date: '2024-01-01T00:00:00Z',
        'project-1-service-a': 100,
        'project-1-service-b': 50,
      },
    ],
    input: [
      {
        date: '2024-01-01T00:00:00Z',
        'project-1-service-a': 60,
        'project-1-service-b': 30,
      },
    ],
    output: [
      {
        date: '2024-01-01T00:00:00Z',
        'project-1-service-a': 40,
        'project-1-service-b': 20,
      },
    ],
  },
};

const defaultProps = {
  projectId: 'project-1',
  apiKeyId: 'api-key-1',
  apiKeyName: 'Test API Key',
};

describe('ApiKeyMetricsDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetchApiKeyDetails.mockResolvedValue({
      ...generateMockApiKey(),
      ttl: '24h',
      groups: [],
    });
    mockFetchApiKeyMetrics.mockResolvedValue(mockMetrics);
    mockDeleteApiKey.mockResolvedValue(undefined);
    mockListAllInferenceDeployments.mockResolvedValue([
      mockDeployment('service-a'),
      mockDeployment('service-b'),
    ]);
  });

  it('renders the api key name in the header', async () => {
    await act(async () => {
      render(<ApiKeyMetricsDashboard {...defaultProps} />, { wrapper });
    });

    await waitFor(() => {
      expect(screen.getByText('Test API Key')).toBeInTheDocument();
    });
  });

  it('fetches metrics with correct from/to params on mount', async () => {
    const before = Date.now();

    await act(async () => {
      render(<ApiKeyMetricsDashboard {...defaultProps} />, { wrapper });
    });

    await waitFor(() => {
      expect(mockFetchApiKeyMetrics).toHaveBeenCalledTimes(1);
    });

    const [projectId, apiKeyId, params] = mockFetchApiKeyMetrics.mock.calls[0];
    expect(projectId).toBe('project-1');
    expect(apiKeyId).toBe('api-key-1');
    expect(params?.start).toBeDefined();
    expect(params?.end).toBeDefined();

    const from = new Date(params!.start!).getTime();
    const to = new Date(params!.end!).getTime();
    // Default period is 24H — range should be ~24h
    expect(to - from).toBeGreaterThanOrEqual(23 * 60 * 60 * 1000);
    expect(to - from).toBeLessThanOrEqual(25 * 60 * 60 * 1000);
    expect(to).toBeGreaterThanOrEqual(before);
  });

  it('renders all five stat card titles', async () => {
    await act(async () => {
      render(<ApiKeyMetricsDashboard {...defaultProps} />, { wrapper });
    });

    expect(screen.getByText('details.stats.totalRequests')).toBeInTheDocument();
    expect(
      screen.getByText('details.stats.successfulRequests'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('details.stats.failedRequests'),
    ).toBeInTheDocument();
    expect(screen.getByText('details.stats.totalTokens')).toBeInTheDocument();
    expect(
      screen.getByText('details.stats.linkedDeployments'),
    ).toBeInTheDocument();
  });

  it('refetches with new time range when selector changes', async () => {
    await act(async () => {
      render(<ApiKeyMetricsDashboard {...defaultProps} />, { wrapper });
    });

    await waitFor(() => {
      expect(mockFetchApiKeyMetrics).toHaveBeenCalledTimes(1);
    });

    const sevenDayTab = screen.getByRole('tab', { name: /7d/i });
    await act(async () => {
      fireEvent.click(sevenDayTab);
    });

    await waitFor(() => {
      expect(mockFetchApiKeyMetrics).toHaveBeenCalledTimes(2);
    });

    const [, , params] = mockFetchApiKeyMetrics.mock.calls[1];
    const from = new Date(params!.start!).getTime();
    const to = new Date(params!.end!).getTime();
    // 7D range
    expect(to - from).toBeGreaterThanOrEqual(6 * 24 * 60 * 60 * 1000);
    expect(to - from).toBeLessThanOrEqual(8 * 24 * 60 * 60 * 1000);
  });

  it('renders edit and delete action buttons', async () => {
    await act(async () => {
      render(<ApiKeyMetricsDashboard {...defaultProps} />, { wrapper });
    });

    expect(screen.getByText('list.actions.edit.title')).toBeInTheDocument();
    expect(screen.getByText('list.actions.delete.title')).toBeInTheDocument();
  });

  it('shows both chart sections', async () => {
    await act(async () => {
      render(<ApiKeyMetricsDashboard {...defaultProps} />, { wrapper });
    });

    expect(
      screen.getByText('details.charts.inferenceRequests.title'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('details.charts.tokenConsumption.title'),
    ).toBeInTheDocument();
  });

  it('shows linked deployments section', async () => {
    await act(async () => {
      render(<ApiKeyMetricsDashboard {...defaultProps} />, { wrapper });
    });

    await waitFor(() => {
      expect(
        screen.getByText('details.linkedDeployments.title'),
      ).toBeInTheDocument();
    });
  });

  it('shows default empty state when no linked deployments', async () => {
    await act(async () => {
      render(<ApiKeyMetricsDashboard {...defaultProps} />, { wrapper });
    });

    await waitFor(() => {
      expect(
        screen.getByText('list.linkedDeployments.empty.description'),
      ).toBeInTheDocument();
    });
  });

  it('shows zero stats when metrics return empty', async () => {
    mockFetchApiKeyMetrics.mockResolvedValue({
      ...mockMetrics,
      stats: {
        totalRequests: 0,
        successfulRequests: 0,
        failedRequests: 0,
        totalTokens: 0,
        linkedDeployments: 0,
      },
    });

    await act(async () => {
      render(<ApiKeyMetricsDashboard {...defaultProps} />, { wrapper });
    });

    await waitFor(() => {
      const zeros = screen.getAllByText('0');
      expect(zeros.length).toBeGreaterThanOrEqual(5);
    });
  });
});

const baseStats = {
  totalRequests: 18,
  successfulRequests: 16,
  failedRequests: 2,
  totalTokens: 900,
  linkedDeployments: 2,
};

const makePoint = (a: number, b: number) => ({
  date: '2026-01-01T00:00:00Z',
  'svc-a': a,
  'svc-b': b,
});

const twoServiceMetrics = {
  stats: baseStats,
  services: ['svc-a', 'svc-b'],
  requestsOverTime: {
    total: [makePoint(30, 10)],
    successful: [makePoint(27, 9)],
    failed: [makePoint(3, 1)],
  },
  tokensOverTime: {
    total: [makePoint(600, 200)],
    input: [makePoint(450, 150)],
    output: [makePoint(150, 50)],
  },
};

describe('computeFilteredStats', () => {
  it('returns stats directly for "all" view', () => {
    const result = computeFilteredStats(twoServiceMetrics, 'all');
    expect(result).toBe(twoServiceMetrics.stats);
  });

  it('returns stats directly when only one service is bound', () => {
    const single = {
      ...twoServiceMetrics,
      services: ['svc-a'],
    };
    expect(computeFilteredStats(single, 'svc-a')).toBe(single.stats);
    expect(computeFilteredStats(single, 'all')).toBe(single.stats);
  });

  it('distributes stats proportionally for a selected service', () => {
    // svc-a has 75% of requests (30/40) and 75% of tokens (600/800)
    const result = computeFilteredStats(twoServiceMetrics, 'svc-a');
    expect(result.successfulRequests).toBe(Math.round(16 * (27 / 36)));
    expect(result.failedRequests).toBe(Math.round(2 * (3 / 4)));
    expect(result.totalRequests).toBe(
      result.successfulRequests + result.failedRequests,
    );
    expect(result.totalTokens).toBe(Math.round(900 * (600 / 800)));
  });

  it('sums to stats totals across both services (up to rounding)', () => {
    const a = computeFilteredStats(twoServiceMetrics, 'svc-a');
    const b = computeFilteredStats(twoServiceMetrics, 'svc-b');
    expect(
      Math.abs(a.totalRequests + b.totalRequests - baseStats.totalRequests),
    ).toBeLessThanOrEqual(1);
    expect(
      Math.abs(a.totalTokens + b.totalTokens - baseStats.totalTokens),
    ).toBeLessThanOrEqual(1);
  });

  it('is stable across different time-range step sizes (overlapping windows)', () => {
    // Simulate the 1h range: same requests but each counted ~5x due to window overlap.
    // The ratio svc-a/(svc-a+svc-b) should remain ~0.75 regardless of the multiplier.
    const overlappingMetrics = {
      ...twoServiceMetrics,
      requestsOverTime: {
        ...twoServiceMetrics.requestsOverTime,
        successful: [
          makePoint(27 * 5, 9 * 5),
          makePoint(27 * 5, 9 * 5),
          makePoint(27 * 5, 9 * 5),
          makePoint(27 * 5, 9 * 5),
          makePoint(27 * 5, 9 * 5),
        ],
        failed: [
          makePoint(3 * 5, 1 * 5),
          makePoint(3 * 5, 1 * 5),
          makePoint(3 * 5, 1 * 5),
          makePoint(3 * 5, 1 * 5),
          makePoint(3 * 5, 1 * 5),
        ],
      },
      tokensOverTime: {
        ...twoServiceMetrics.tokensOverTime,
        total: [
          makePoint(600 * 5, 200 * 5),
          makePoint(600 * 5, 200 * 5),
          makePoint(600 * 5, 200 * 5),
          makePoint(600 * 5, 200 * 5),
          makePoint(600 * 5, 200 * 5),
        ],
      },
    };

    const normal = computeFilteredStats(twoServiceMetrics, 'svc-a');
    const overlapping = computeFilteredStats(overlappingMetrics, 'svc-a');

    expect(overlapping.successfulRequests).toBe(normal.successfulRequests);
    expect(overlapping.failedRequests).toBe(normal.failedRequests);
    expect(overlapping.totalTokens).toBe(normal.totalTokens);
  });

  it('returns zero stats when time-series has no data for any service', () => {
    const empty = {
      ...twoServiceMetrics,
      requestsOverTime: {
        total: [makePoint(0, 0)],
        successful: [makePoint(0, 0)],
        failed: [makePoint(0, 0)],
      },
      tokensOverTime: {
        total: [makePoint(0, 0)],
        input: [makePoint(0, 0)],
        output: [makePoint(0, 0)],
      },
    };
    const result = computeFilteredStats(empty, 'svc-a');
    expect(result.totalRequests).toBe(0);
    expect(result.totalTokens).toBe(0);
  });
});
