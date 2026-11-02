// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { render, screen, fireEvent } from '@testing-library/react';
import { vi } from 'vitest';

import { InferenceMetrics } from '@/components/features/workloads/InferenceMetrics';
import { TimeRangePeriod } from '@amdenterpriseai/types';
import { TimeRange } from '@amdenterpriseai/types';

import wrapper from '@/__tests__/ProviderWrapper';

// Mock the ProjectContext
vi.mock('@/contexts/ProjectContext', () => ({
  useProject: () => ({
    activeProject: 'test-project-id',
  }),
}));

// Mock next-i18next
vi.mock('next-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

// Mock the time range utility and formatters
const mockGetCurrentTimeRange = vi.fn(() => ({
  start: new Date('2024-01-01T00:00:00Z'),
  end: new Date('2024-01-01T01:00:00Z'),
}));

vi.mock('@amdenterpriseai/utils/app', () => ({
  getCurrentTimeRange: () => mockGetCurrentTimeRange(),
  formatSeconds: vi.fn((v: number) => `${v}s`),
  formatTokens: vi.fn((v: number) => `${v}t`),
  displayPercentage: vi.fn((v: number) => `${v}%`),
}));

// Mock the ChartTimeSelector component
vi.mock('@amdenterpriseai/components', () => ({
  ChartTimeSelector: vi.fn(
    ({
      onTimeRangeChange,
      onChartsRefresh,
      initialTimePeriod,
      translationPrefix,
      isFetching,
      lastFetchedTimestamp,
    }) => (
      <div data-testid="chart-time-selector">
        <button
          data-testid="time-range-button"
          onClick={() =>
            onTimeRangeChange(TimeRangePeriod['24H'], {
              start: new Date('2024-01-01T00:00:00Z'),
              end: new Date('2024-01-01T06:00:00Z'),
            })
          }
        >
          Change Time Range
        </button>
        <button data-testid="refresh-button" onClick={onChartsRefresh}>
          Refresh
        </button>
        <div data-testid="initial-period">{initialTimePeriod}</div>
        <div data-testid="translation-prefix">{translationPrefix}</div>
        <div data-testid="is-fetching">{isFetching ? 'true' : 'false'}</div>
        <div data-testid="last-fetched">
          {lastFetchedTimestamp?.toISOString()}
        </div>
      </div>
    ),
  ),
}));

// Mock the generic metric card components
vi.mock('@/components/features/workloads/ScalarMetricCard', () => ({
  ScalarMetricCard: vi.fn(({ config, workloadId, timeRange }) => (
    <div data-testid={`scalar-card-${config.metric}`}>
      <div data-testid="workload-id">{workloadId}</div>
      <div data-testid="time-range">{JSON.stringify(timeRange)}</div>
    </div>
  )),
}));

vi.mock('@/components/features/workloads/TimeseriesMetricCard', () => ({
  TimeseriesMetricCard: vi.fn(({ config, workloadId, timeRange }) => (
    <div data-testid={`timeseries-card-${config.metric}`}>
      <div data-testid="workload-id">{workloadId}</div>
      <div data-testid="time-range">{JSON.stringify(timeRange)}</div>
    </div>
  )),
}));

vi.mock('@/components/features/workloads/InferenceRequestsCard', () => ({
  default: vi.fn(({ workloadId, timePeriod }) => (
    <div data-testid="inference-requests-card">
      <div data-testid="workload-id">{workloadId}</div>
      <div data-testid="time-range-period">{timePeriod}</div>
    </div>
  )),
}));

// Mock GPU card components
vi.mock('@/components/features/projects', () => ({
  GPUDeviceUsageCard: vi.fn(() => <div data-testid="gpu-device-usage-card" />),
  GPUMemoryUsageCard: vi.fn(() => <div data-testid="gpu-memory-usage-card" />),
  CPUCoreUsageCard: vi.fn(() => <div data-testid="cpu-core-usage-card" />),
  SystemMemoryUsageCard: vi.fn(() => (
    <div data-testid="system-memory-usage-card" />
  )),
}));

// Mock metrics fetch
vi.mock('@/lib/app/metrics', () => ({
  getTimeseriesMetric: vi.fn(() =>
    Promise.resolve({ data: [], range: { timestamps: [] } }),
  ),
}));

// Mock useIsFetching hook and useQueryClient
const mockUseIsFetching = vi.fn();
const mockInvalidateQueries = vi.fn();
const mockUseQueryClient = vi.fn(() => ({
  invalidateQueries: mockInvalidateQueries,
}));

vi.mock('@tanstack/react-query', async () => {
  const actual = await vi.importActual('@tanstack/react-query');
  return {
    ...actual,
    useIsFetching: () => mockUseIsFetching(),
    useQueryClient: () => mockUseQueryClient(),
  };
});

describe('InferenceMetrics', () => {
  const workloadId = 'workload-1';

  const defaultTimeRange: TimeRange = {
    start: new Date('2024-01-01T00:00:00Z'),
    end: new Date('2024-01-01T01:00:00Z'),
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    mockUseIsFetching.mockReturnValue(0);
    mockInvalidateQueries.mockClear();
    mockGetCurrentTimeRange.mockClear();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders the inference metrics component with all metric cards', () => {
    render(<InferenceMetrics workloadId={workloadId} />, {
      wrapper,
    });

    // Check ChartTimeSelector
    expect(screen.getByTestId('chart-time-selector')).toBeInTheDocument();
    expect(screen.getByTestId('initial-period')).toHaveTextContent('15m');
    expect(screen.getByTestId('translation-prefix')).toHaveTextContent(
      'timeRange',
    );

    // Timeseries latency cards
    expect(
      screen.getByTestId('timeseries-card-time_to_first_token_seconds'),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('timeseries-card-inter_token_latency_seconds'),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('timeseries-card-e2e_request_latency_seconds'),
    ).toBeInTheDocument();

    // Inference requests chart
    expect(screen.getByTestId('inference-requests-card')).toBeInTheDocument();

    // Scalar cards
    expect(screen.getByTestId('scalar-card-max_requests')).toBeInTheDocument();
    expect(screen.getByTestId('scalar-card-min_requests')).toBeInTheDocument();
    expect(screen.getByTestId('scalar-card-avg_requests')).toBeInTheDocument();
    expect(
      screen.getByTestId('scalar-card-total_requests'),
    ).toBeInTheDocument();
    expect(screen.getByTestId('scalar-card-total_tokens')).toBeInTheDocument();
    expect(
      screen.getByTestId('scalar-card-kv_cache_usage'),
    ).toBeInTheDocument();

    // GPU cards
    expect(screen.getByTestId('gpu-device-usage-card')).toBeInTheDocument();
    expect(screen.getByTestId('gpu-memory-usage-card')).toBeInTheDocument();
    expect(screen.getByTestId('cpu-core-usage-card')).toBeInTheDocument();
    expect(screen.getByTestId('system-memory-usage-card')).toBeInTheDocument();
  });

  it('passes correct props to metric cards', () => {
    render(<InferenceMetrics workloadId={workloadId} />, {
      wrapper,
    });

    const workloadIdElements = screen.getAllByTestId('workload-id');
    workloadIdElements.forEach((element) => {
      expect(element).toHaveTextContent('workload-1');
    });

    // TimeseriesMetricCard and ScalarMetricCard have time-range test IDs
    const timeRangeElements = screen.getAllByTestId('time-range');
    expect(timeRangeElements.length).toBeGreaterThan(0);
    timeRangeElements.forEach((element) => {
      expect(element).toHaveTextContent(JSON.stringify(defaultTimeRange));
    });

    // InferenceRequestsCard receives timePeriod, not timeRange
    expect(screen.getByTestId('time-range-period')).toHaveTextContent('15m');
  });

  it('handles time range changes', () => {
    render(<InferenceMetrics workloadId={workloadId} />, {
      wrapper,
    });

    const timeRangeButton = screen.getByTestId('time-range-button');
    fireEvent.click(timeRangeButton);

    // TimeseriesMetricCard and ScalarMetricCard should receive updated timeRange
    const timeRangeElements = screen.getAllByTestId('time-range');
    const newTimeRange = {
      start: new Date('2024-01-01T00:00:00Z'),
      end: new Date('2024-01-01T06:00:00Z'),
    };
    expect(timeRangeElements.length).toBeGreaterThan(0);
    timeRangeElements.forEach((element) => {
      expect(element).toHaveTextContent(JSON.stringify(newTimeRange));
    });
  });

  it('shows fetching state correctly', () => {
    mockUseIsFetching.mockReturnValue(1);

    render(<InferenceMetrics workloadId={workloadId} />, {
      wrapper,
    });

    expect(screen.getByTestId('is-fetching')).toHaveTextContent('true');
  });

  it('shows not fetching state correctly', () => {
    mockUseIsFetching.mockReturnValue(0);

    render(<InferenceMetrics workloadId={workloadId} />, {
      wrapper,
    });

    expect(screen.getByTestId('is-fetching')).toHaveTextContent('false');
  });

  it('handles charts refresh correctly', () => {
    render(<InferenceMetrics workloadId={workloadId} />, {
      wrapper,
    });

    const refreshButton = screen.getByTestId('refresh-button');
    fireEvent.click(refreshButton);

    expect(mockGetCurrentTimeRange).toHaveBeenCalled();
    expect(mockInvalidateQueries).not.toHaveBeenCalled();
  });

  it('handles refresh when time range has changed', () => {
    render(<InferenceMetrics workloadId={workloadId} />, {
      wrapper,
    });

    const refreshButton = screen.getByTestId('refresh-button');

    expect(() => fireEvent.click(refreshButton)).not.toThrow();

    expect(
      screen.getByText('details.sections.inferenceMetrics'),
    ).toBeInTheDocument();
  });

  it('updates last fetched timestamp when not fetching', () => {
    const mockDate = new Date('2022-01-01T00:00:00.000Z');
    vi.setSystemTime(mockDate);

    mockUseIsFetching.mockReturnValue(0);

    render(<InferenceMetrics workloadId={workloadId} />, {
      wrapper,
    });

    expect(screen.getByTestId('last-fetched')).toHaveTextContent(
      '2022-01-01T00:00:00.000Z',
    );
  });

  it('invalidates queries when time range changes', () => {
    render(<InferenceMetrics workloadId={workloadId} />, {
      wrapper,
    });

    const timeRangeButton = screen.getByTestId('time-range-button');
    fireEvent.click(timeRangeButton);

    expect(mockInvalidateQueries).toHaveBeenCalledWith({
      queryKey: [
        'project',
        'test-project-id',
        'workload',
        'workload-1',
        'metrics',
      ],
    });
  });
});
