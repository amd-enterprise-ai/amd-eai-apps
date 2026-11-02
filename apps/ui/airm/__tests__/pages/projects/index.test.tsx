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

import { Cluster } from '@/types/clusters';
import { ClusterStatus } from '@/types/enums/cluster-status';
import { ProjectStatus } from '@/types/enums/projects';
import { QuotaResource, QuotaStatus } from '@/types/enums/quotas';
import {
  GPU_PREEMPTION_DISABLED,
  ProjectWithResourceAllocation,
} from '@/types/projects';

import ProjectsPage from '@/pages/projects';

import wrapper from '@/__tests__/ProviderWrapper';
import '@testing-library/jest-dom';
import { fetchProjects } from '@/services/app';
import { cloneDeep } from 'lodash';
import { DEFAULT_REFETCH_INTERVAL_FOR_PENDING_DATA } from '@amdenterpriseai/utils/app';

vi.mock(import('@/services/app'), async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    fetchProjects: vi.fn(),
  };
});

const generateMockProjects = (
  count: number,
): ProjectWithResourceAllocation[] => {
  return Array.from({ length: count }, (_, i) => ({
    id: (i + 1).toString(),
    clusterId: `c${(i % 2) + 1}`, // Assign to c1 or c2
    name: `Project Name ${i + 1}`,
    description: `Description ${i + 1}`,
    status: ProjectStatus.READY,
    statusReason: null,
    quota: {
      status: QuotaStatus.READY,
      cpuMilliCores: 1000,
      gpuCount: 1,
      memoryBytes: 2000 + i * 1000,
      ephemeralStorageBytes: 10000,
    },
    cluster: {
      id: '1',
      name: 'cluster-1',
      lastHeartbeatAt: '2025-03-11T23:24:03.733668Z',
      status: ClusterStatus.HEALTHY,
    },
    gpuAllocationPercentage: 100.0,
    cpuAllocationPercentage: 25.0,
    memoryAllocationPercentage: 25.0 + i * 5,
    gpuAllocationExceeded: false,
    cpuAllocationExceeded: false,
    memoryAllocationExceeded: false,
    gpuPreemption: GPU_PREEMPTION_DISABLED,
  }));
};

const mockClusters: Cluster[] = [
  {
    id: 'c1',
    name: 'Test Cluster 1',
    status: ClusterStatus.HEALTHY,
    lastHeartbeatAt: new Date().toISOString(),
    availableResources: {
      [QuotaResource.CPU]: 8000, // Example value
      [QuotaResource.RAM]: 32 * 1024 * 1024 * 1024,
      [QuotaResource.DISK]: 500 * 1024 * 1024 * 1024,
      [QuotaResource.GPU]: 4,
    },
    allocatedResources: {
      [QuotaResource.CPU]: 2000,
      [QuotaResource.RAM]: 8 * 1024 * 1024 * 1024,
      [QuotaResource.DISK]: 100 * 1024 * 1024 * 1024,
      [QuotaResource.GPU]: 1,
    },
    gpuAllocationPercentage: 25.0,
    cpuAllocationPercentage: 25.0,
    memoryAllocationPercentage: 25.0,
    totalNodeCount: 0,
    availableNodeCount: 0,
    assignedQuotaCount: 0,
    createdAt: new Date().toISOString(),
  },
  {
    id: 'c2',
    name: 'Test Cluster 2',
    status: ClusterStatus.HEALTHY,
    lastHeartbeatAt: new Date().toISOString(),
    availableResources: {
      [QuotaResource.CPU]: 16000,
      [QuotaResource.RAM]: 64 * 1024 * 1024 * 1024,
      [QuotaResource.DISK]: 1000 * 1024 * 1024 * 1024,
      [QuotaResource.GPU]: 8,
    },
    allocatedResources: {
      [QuotaResource.CPU]: 4000,
      [QuotaResource.RAM]: 16 * 1024 * 1024 * 1024,
      [QuotaResource.DISK]: 200 * 1024 * 1024 * 1024,
      [QuotaResource.GPU]: 2,
    },
    gpuAllocationPercentage: 25.0,
    cpuAllocationPercentage: 25.0,
    memoryAllocationPercentage: 25.0,
    totalNodeCount: 0,
    availableNodeCount: 0,
    assignedQuotaCount: 0,
    createdAt: new Date().toISOString(),
  },
];

describe('projects', () => {
  it('should not crash the page', async () => {
    const mockProjects = generateMockProjects(0);
    const { container } = render(
      <ProjectsPage projects={mockProjects} clusters={mockClusters} />,
      { wrapper },
    );
    expect(container).toBeTruthy();
  });

  it('should render a list of projects', async () => {
    const mockProjects = generateMockProjects(5);
    await act(() => {
      render(<ProjectsPage projects={mockProjects} clusters={mockClusters} />, {
        wrapper,
      });
    });

    mockProjects.forEach((project) => {
      expect(screen.getByText(project.name)).toBeInTheDocument();
    });
  });

  it('refetches the data if project is pending', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const mockProjects = generateMockProjects(1);
    mockProjects[0].status = ProjectStatus.PENDING;

    // Immediately after page load
    vi.mocked(fetchProjects).mockResolvedValueOnce({
      data: mockProjects,
    });

    let readyProjects = cloneDeep(mockProjects);
    readyProjects[0].status = ProjectStatus.READY;
    // After 10 seconds, synced
    vi.mocked(fetchProjects).mockResolvedValueOnce({
      data: readyProjects,
    });

    await act(async () => {
      render(<ProjectsPage projects={mockProjects} clusters={mockClusters} />, {
        wrapper,
      });
    });

    // On page load
    expect(fetchProjects).toBeCalledTimes(1);

    // After 10 seconds, synced secret
    await act(() =>
      vi.advanceTimersByTimeAsync(DEFAULT_REFETCH_INTERVAL_FOR_PENDING_DATA),
    );
    expect(fetchProjects).toBeCalledTimes(2);

    // No more polling
    await act(() =>
      vi.advanceTimersByTimeAsync(DEFAULT_REFETCH_INTERVAL_FOR_PENDING_DATA),
    );
    expect(fetchProjects).toBeCalledTimes(2);

    vi.useRealTimers();
  });

  it('should filter the list of projects based on name', async () => {
    const mockProjects = generateMockProjects(5);
    await act(async () => {
      render(<ProjectsPage projects={mockProjects} clusters={mockClusters} />, {
        wrapper,
      });
    });

    const filterInput = screen.getByPlaceholderText(
      'list.filter.search.placeholder',
    );
    expect(filterInput).toBeInTheDocument();

    // Simulate user typing in the filter input
    await fireEvent.change(filterInput, {
      target: { value: 'Project Name 2' },
    });

    await waitFor(() => {
      // Check that only the filtered project is displayed
      expect(screen.getByText('Project Name 2')).toBeInTheDocument();
      expect(screen.queryByText('Project Name 1')).not.toBeInTheDocument();
      expect(screen.queryByText('Project Name 3')).not.toBeInTheDocument();
      expect(screen.queryByText('Project Name 4')).not.toBeInTheDocument();
      expect(screen.queryByText('Project Name 5')).not.toBeInTheDocument();
    });
  });

  it('should filter the list of projects based on cluster', async () => {
    const mockProjects = generateMockProjects(4);
    await act(async () => {
      render(<ProjectsPage projects={mockProjects} clusters={mockClusters} />, {
        wrapper,
      });
    });

    // Open the cluster select dropdown
    const clusterSelect = screen.getByRole('button', {
      name: /list\.filter\.cluster/,
    });
    await fireEvent.click(clusterSelect);

    const clusterOption = await screen.findByRole('option', {
      name: 'Test Cluster 1',
    });
    await fireEvent.click(clusterOption);

    // Projects in c1 (Project Name 1, Project Name 3) should be visible
    expect(screen.getByText('Project Name 1')).toBeInTheDocument();
    expect(screen.getByText('Project Name 3')).toBeInTheDocument();

    // Projects in c2 (Project Name 2, Project Name 4) should not be visible
    expect(screen.queryByText('Project Name 2')).not.toBeInTheDocument();
    expect(screen.queryByText('Project Name 4')).not.toBeInTheDocument();
  });

  it('should filter the list of projects based on status', async () => {
    const mockProjects = generateMockProjects(4);
    mockProjects[1].status = ProjectStatus.PENDING;
    mockProjects[3].status = ProjectStatus.PENDING;

    await act(async () => {
      render(<ProjectsPage projects={mockProjects} clusters={mockClusters} />, {
        wrapper,
      });
    });

    const statusSelect = screen.getByRole('button', {
      name: /list\.filter\.status/,
    });
    await fireEvent.click(statusSelect);

    // Select "READY" status
    await waitFor(() => {
      expect(
        screen.getByRole('option', {
          name: `status.${ProjectStatus.READY}`,
        }),
      ).toBeInTheDocument();
    });

    const readyOption = screen.getByRole('option', {
      name: `status.${ProjectStatus.READY}`,
    });
    await fireEvent.click(readyOption);

    // Projects with READY status (Project Name 1, Project Name 3 based on mockQuotas logic) should be visible
    expect(screen.getByText('Project Name 1')).toBeInTheDocument();
    expect(screen.getByText('Project Name 3')).toBeInTheDocument();

    // Projects with PENDING status (Project Name 2, Project Name 4) should not be visible
    await waitFor(() => {
      expect(screen.queryByText('Project Name 2')).not.toBeInTheDocument();
      expect(screen.queryByText('Project Name 4')).not.toBeInTheDocument();
    });
  });

  it('should show all projects when cluster filter is selected then deselected', async () => {
    const mockProjects = generateMockProjects(4);
    await act(async () => {
      render(<ProjectsPage projects={mockProjects} clusters={mockClusters} />, {
        wrapper,
      });
    });

    // Open the cluster select dropdown and select "Test Cluster 1"
    const clusterSelect = screen.getByRole('button', {
      name: /list\.filter\.cluster/,
    });
    await fireEvent.click(clusterSelect);
    const clusterOption = await screen.findByRole('option', {
      name: 'Test Cluster 1',
    });
    await fireEvent.click(clusterOption);

    // Only c1 projects should be visible after selecting
    expect(screen.getByText('Project Name 1')).toBeInTheDocument();
    expect(screen.getByText('Project Name 3')).toBeInTheDocument();
    expect(screen.queryByText('Project Name 2')).not.toBeInTheDocument();
    expect(screen.queryByText('Project Name 4')).not.toBeInTheDocument();

    // Clear the cluster filter (v3 single-select does not toggle off on re-click)
    const clearFiltersButton = screen.getByRole('button', {
      name: /actions\.clearFilters/,
    });
    await act(async () => {
      fireEvent.click(clearFiltersButton);
    });

    // All projects should be visible again (not filtered out by empty array)
    await waitFor(() => {
      mockProjects.forEach((project) => {
        expect(screen.getByText(project.name)).toBeInTheDocument();
      });
    });
  });

  it('should show all projects when status filter is selected then deselected', async () => {
    const mockProjects = generateMockProjects(4);
    mockProjects[1].status = ProjectStatus.PENDING;
    mockProjects[3].status = ProjectStatus.PENDING;

    await act(async () => {
      render(<ProjectsPage projects={mockProjects} clusters={mockClusters} />, {
        wrapper,
      });
    });

    // Open the status select dropdown
    const statusSelect = screen.getByRole('button', {
      name: /list\.filter\.status/,
    });
    await fireEvent.click(statusSelect);

    // Select "READY" status
    await waitFor(() => {
      expect(
        screen.getByRole('option', {
          name: `status.${ProjectStatus.READY}`,
        }),
      ).toBeInTheDocument();
    });

    const readyOption = screen.getByRole('option', {
      name: `status.${ProjectStatus.READY}`,
    });
    await fireEvent.click(readyOption);

    // Only READY projects should be visible
    await waitFor(() => {
      expect(screen.getByText('Project Name 1')).toBeInTheDocument();
      expect(screen.getByText('Project Name 3')).toBeInTheDocument();
      expect(screen.queryByText('Project Name 2')).not.toBeInTheDocument();
      expect(screen.queryByText('Project Name 4')).not.toBeInTheDocument();
    });

    // Clear the status filter (v3 single-select does not toggle off on re-click)
    const clearFiltersButton = screen.getByRole('button', {
      name: /actions\.clearFilters/,
    });
    await act(async () => {
      fireEvent.click(clearFiltersButton);
    });

    // All projects should be visible again (not filtered out by empty array)
    await waitFor(() => {
      mockProjects.forEach((project) => {
        expect(screen.getByText(project.name)).toBeInTheDocument();
      });
    });
  });

  it('should clear all filters when "Clear Filters" button is clicked', async () => {
    const mockProjects = generateMockProjects(5);
    await act(async () => {
      render(<ProjectsPage projects={mockProjects} clusters={mockClusters} />, {
        wrapper,
      });
    });

    // Apply a name filter
    const nameFilterInput = screen.getByPlaceholderText(
      'list.filter.search.placeholder',
    );
    await fireEvent.change(nameFilterInput, {
      target: { value: 'Project Name 1' },
    });
    await waitFor(() => {
      expect(screen.getByText('Project Name 1')).toBeInTheDocument();
      expect(screen.queryByText('Project Name 2')).not.toBeInTheDocument();
    });

    // Apply a cluster filter
    const clusterSelect = screen.getByText('list.filter.cluster.placeholder'); // Changed to use data-testid
    await fireEvent.click(clusterSelect);
    const cluster1Options = await screen.getAllByText('Test Cluster 1'); // Assuming "Name 1" is in "Test Cluster 1"
    await fireEvent.click(cluster1Options[0]);

    expect(screen.getByText('Project Name 1')).toBeInTheDocument();

    const clearFiltersButton = screen.getByText('actions.clearFilters.title'); // Using the translation key
    await fireEvent.click(clearFiltersButton);

    // All projects should be visible again
    await waitFor(() => {
      mockProjects.forEach((project) => {
        expect(screen.getByText(project.name)).toBeInTheDocument();
      });
    });

    await waitFor(() => {
      expect(nameFilterInput).toHaveValue('');
      expect(clusterSelect).toHaveTextContent(
        'list.filter.cluster.placeholder',
      );
    });
  });
});
