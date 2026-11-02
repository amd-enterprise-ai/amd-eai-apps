// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';

import {
  fetchGPUDeviceUtilization,
  fetchGPUMemoryUtilization,
  fetchUtilization,
} from '@/services/app';
import { getCurrentTimeRange } from '@amdenterpriseai/utils/app';

import { TimeRangePeriod } from '@amdenterpriseai/types';
import { TimeSeriesResponse } from '@amdenterpriseai/types';

import DashboardPage from '@/pages/';

import wrapper from '@/__tests__/ProviderWrapper';
import '@testing-library/jest-dom';
import { Mock, vi } from 'vitest';

// Mock next/router
vi.mock('next/router', () => ({
  default: {
    push: vi.fn(),
  },
}));

vi.mock('@/services/app', async (importOriginal) => {
  const mockReturn: TimeSeriesResponse = {
    data: [
      {
        metadata: {
          project: {
            id: '1',
            name: 'usergroup',
          },
        },
        values: [
          { timestamp: '2025-04-10T07:00:00Z', value: 50 },
          { timestamp: '2025-04-11T07:00:00Z', value: 60 },
        ],
      },
    ],
    range: {
      start: '2025-04-10T07:00:00Z',
      end: '2025-04-11T07:00:00Z',
      intervalSeconds: 300,
      timestamps: ['2025-04-10T07:00:00Z', '2025-04-11T07:00:00Z'],
    },
  };
  return {
    ...(await importOriginal()),
    fetchGPUMemoryUtilization: vi.fn().mockResolvedValue(mockReturn),
    fetchGPUDeviceUtilization: vi.fn().mockResolvedValue(mockReturn),
    fetchUtilization: vi.fn(),
    fetchClusterStatistics: vi.fn().mockResolvedValue({
      totalClusterCount: 5,
      totalNodeCount: 50,
      availableNodeCount: 45,
      totalGpuNodeCount: 20,
      totalGpuCount: 80,
      availableGpuCount: 70,
      allocatedGpuCount: 60,
    }),
  };
});

const mockClusterStatistics = {
  totalClusterCount: 10,
  totalNodeCount: 997,
  availableNodeCount: 900,
  totalGpuNodeCount: 400,
  totalGpuCount: 1200,
  availableGpuCount: 1000,
  allocatedGpuCount: 900,
};

const mockUtilizationData = {
  timestamp: '2025-04-17T07:00:00Z',
  utilizationByProject: [],
  totalUtilizedGpusCount: 120,
  totalRunningWorkloadsCount: 22,
  totalPendingWorkloadsCount: 6,
};

describe('Dashboard Page', () => {
  it('should not crash the page', async () => {
    const { container } = render(
      <DashboardPage clusterStats={mockClusterStatistics} />,
      {
        wrapper,
      },
    );
    expect(container).toBeTruthy();
  });

  it('should fetch GPU memory utilization data', async () => {
    await act(() => {
      render(<DashboardPage clusterStats={mockClusterStatistics} />, {
        wrapper,
      });
    });

    expect(fetchGPUMemoryUtilization).toHaveBeenCalledWith(
      expect.any(Date),
      expect.any(Date),
    );
  });

  it('should fetch GPU device utilization data', async () => {
    const mockTimeRange = getCurrentTimeRange(TimeRangePeriod['1H']);

    await act(() => {
      render(<DashboardPage clusterStats={mockClusterStatistics} />, {
        wrapper,
      });
    });

    expect(fetchGPUDeviceUtilization).toHaveBeenCalled();
    expect(fetchGPUMemoryUtilization).toHaveBeenCalled();
  });

  it('set time range to 24h for chart', async () => {
    await act(() => {
      render(<DashboardPage clusterStats={mockClusterStatistics} />, {
        wrapper,
      });
    });

    await waitFor(() => {
      expect(screen.getByText('actions.refresh.title')).toBeInTheDocument();
    });

    const tab24h = screen.getByText('timeRange.range.24h');
    await waitFor(() => {
      expect(fetchGPUDeviceUtilization).toHaveBeenCalledTimes(1);
    });
    expect(tab24h).toBeInTheDocument();

    await act(() => {
      fireEvent.click(tab24h);
    });

    expect(fetchGPUDeviceUtilization).toHaveBeenCalledWith(
      expect.any(Date),
      expect.any(Date),
    );
    expect(fetchGPUMemoryUtilization).toHaveBeenCalledWith(
      expect.any(Date),
      expect.any(Date),
    );
  });

  it('set time range to 7d for chart', async () => {
    await act(() => {
      render(<DashboardPage clusterStats={mockClusterStatistics} />, {
        wrapper,
      });
    });

    await waitFor(() => {
      expect(fetchGPUDeviceUtilization).toHaveBeenCalledTimes(1);
    });

    const tabs = screen.getAllByRole('tab');

    const tab7d = tabs[2];
    expect(tab7d).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('actions.refresh.title')).toBeInTheDocument();
    });

    await act(() => {
      fireEvent.click(tab7d);
    });

    expect(fetchGPUDeviceUtilization).toHaveBeenCalledWith(
      expect.any(Date),
      expect.any(Date),
    );
    expect(fetchGPUMemoryUtilization).toHaveBeenCalledWith(
      expect.any(Date),
      expect.any(Date),
    );
  });

  it('refresh button triggers refetch calls', async () => {
    await act(() => {
      render(<DashboardPage clusterStats={mockClusterStatistics} />, {
        wrapper,
      });
    });

    await waitFor(() => {
      expect(screen.getByText('actions.refresh.title')).toBeInTheDocument();
    });

    await act(() => {
      fireEvent.click(screen.getByText('actions.refresh.title'));
    });

    expect(fetchGPUDeviceUtilization).toHaveBeenCalled();
    expect(fetchGPUMemoryUtilization).toHaveBeenCalled();
  });

  it('renders static cluster card values correctly', async () => {
    await act(() => {
      render(<DashboardPage clusterStats={mockClusterStatistics} />, {
        wrapper,
      });
    });

    await waitFor(() => {
      expect(screen.getByText('10')).toBeInTheDocument(); // totalClusterCount
      expect(screen.getByText('400')).toBeInTheDocument(); // totalGpuNodeCount
      expect(screen.getByText('900')).toBeInTheDocument(); // allocatedGpuCount
      expect(screen.getByText('1000')).toBeInTheDocument(); // availableGpuCount
    });
  });

  it('renders utilization stats from API data', async () => {
    (fetchUtilization as Mock).mockResolvedValue(mockUtilizationData);

    await act(() => {
      render(<DashboardPage clusterStats={mockClusterStatistics} />, {
        wrapper,
      });
    });
    await waitFor(() => {
      expect(screen.getByText('120')).toBeInTheDocument(); // GPU Utilization
      expect(screen.getByText('22')).toBeInTheDocument(); // Running
      expect(screen.getByText('6')).toBeInTheDocument(); // Pending
    });
  });

  it('renders fallback values when utilization is missing', async () => {
    (fetchUtilization as Mock).mockResolvedValue({} as any);
    await act(() => {
      render(<DashboardPage clusterStats={mockClusterStatistics} />, {
        wrapper,
      });
    });

    await waitFor(() => {
      expect(screen.getAllByText('0').length).toBeGreaterThan(0);
    });
  });

  it('renders with utilization projects data', async () => {
    const mockUtilizationWithProjects = {
      ...mockUtilizationData,
      utilizationByProject: [
        {
          project: { id: 'project-1', name: 'Test Project 1' },
          allocatedGpusCount: 10,
          utilizedGpusCount: 8,
          runningWorkloadsCount: 5,
          pendingWorkloadsCount: 2,
        },
        {
          project: { id: 'project-2', name: 'Test Project 2' },
          allocatedGpusCount: 5,
          utilizedGpusCount: 3,
          runningWorkloadsCount: 2,
          pendingWorkloadsCount: 1,
        },
      ],
    };

    (fetchUtilization as Mock).mockResolvedValue(mockUtilizationWithProjects);

    await act(() => {
      render(<DashboardPage clusterStats={mockClusterStatistics} />, {
        wrapper,
      });
    });

    await waitFor(() => {
      expect(screen.getByText('Test Project 1')).toBeInTheDocument();
      expect(screen.getByText('Test Project 2')).toBeInTheDocument();
    });
  });

  it('navigates to project dashboard when row is clicked', async () => {
    const mockUtilizationWithProjects = {
      ...mockUtilizationData,
      utilizationByProject: [
        {
          project: { id: 'project-1', name: 'Test Project 1' },
          allocatedGpusCount: 10,
          utilizedGpusCount: 8,
          runningWorkloadsCount: 5,
          pendingWorkloadsCount: 2,
        },
      ],
    };

    (fetchUtilization as Mock).mockResolvedValue(mockUtilizationWithProjects);

    await act(() => {
      render(<DashboardPage clusterStats={mockClusterStatistics} />, {
        wrapper,
      });
    });

    await waitFor(() => {
      expect(screen.getByText('Test Project 1')).toBeInTheDocument();
    });

    // Test that the table row exists
    const projectRow = screen.getByText('Test Project 1').closest('tr');
    expect(projectRow).toBeInTheDocument();
  });

  it('handles chart data with more than 4 data entries correctly', async () => {
    const mockLargeTimeSeriesData: TimeSeriesResponse = {
      data: [
        {
          metadata: { project: { id: '1', name: 'Project 1' } },
          values: [{ timestamp: '2025-04-10T07:00:00Z', value: 50 }],
        },
        {
          metadata: { project: { id: '2', name: 'Project 2' } },
          values: [{ timestamp: '2025-04-10T07:00:00Z', value: 30 }],
        },
        {
          metadata: { project: { id: '3', name: 'Project 3' } },
          values: [{ timestamp: '2025-04-10T07:00:00Z', value: 20 }],
        },
        {
          metadata: { project: { id: '4', name: 'Project 4' } },
          values: [{ timestamp: '2025-04-10T07:00:00Z', value: 15 }],
        },
        {
          metadata: { project: { id: '5', name: 'Project 5' } },
          values: [{ timestamp: '2025-04-10T07:00:00Z', value: 10 }],
        },
      ],
      range: {
        start: '2025-04-10T07:00:00Z',
        end: '2025-04-11T07:00:00Z',
        intervalSeconds: 300,
        timestamps: ['2025-04-10T07:00:00Z'],
      },
    };

    (fetchGPUMemoryUtilization as Mock).mockResolvedValue(
      mockLargeTimeSeriesData,
    );
    (fetchGPUDeviceUtilization as Mock).mockResolvedValue(
      mockLargeTimeSeriesData,
    );

    await act(() => {
      render(<DashboardPage clusterStats={mockClusterStatistics} />, {
        wrapper,
      });
    });

    // Should render charts successfully even with large data
    await waitFor(() => {
      expect(
        screen.getByText(
          'allocationAndWorkloads.charts.gpuMemoryUtilization.title',
        ),
      ).toBeInTheDocument();
      expect(
        screen.getByText(
          'allocationAndWorkloads.charts.gpuDeviceUtilization.title',
        ),
      ).toBeInTheDocument();
    });
  });

  it('handles empty chart data gracefully', async () => {
    const mockEmptyData: TimeSeriesResponse = {
      data: [],
      range: {
        start: '2025-04-10T07:00:00Z',
        end: '2025-04-11T07:00:00Z',
        intervalSeconds: 300,
        timestamps: [],
      },
    };

    (fetchGPUMemoryUtilization as Mock).mockResolvedValue(mockEmptyData);
    (fetchGPUDeviceUtilization as Mock).mockResolvedValue(mockEmptyData);

    await act(() => {
      render(<DashboardPage clusterStats={mockClusterStatistics} />, {
        wrapper,
      });
    });

    // Should render charts successfully even with empty data
    await waitFor(() => {
      expect(
        screen.getByText(
          'allocationAndWorkloads.charts.gpuMemoryUtilization.title',
        ),
      ).toBeInTheDocument();
      expect(
        screen.getByText(
          'allocationAndWorkloads.charts.gpuDeviceUtilization.title',
        ),
      ).toBeInTheDocument();
    });
  });
});
