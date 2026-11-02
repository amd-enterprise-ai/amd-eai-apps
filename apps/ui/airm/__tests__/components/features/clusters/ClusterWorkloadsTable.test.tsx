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
import { format } from 'date-fns';

import { fetchClusterWorkloadsMetrics } from '@/services/app';
import { getClusterProjects } from '@/services/app';
import { deleteWorkload } from '@/services/app';

import { ClusterWorkloadsTable } from '@/components/features/clusters';

import wrapper from '@/__tests__/ProviderWrapper';

const generateClusterWorkloadsMetrics = (
  n: number,
  clusterId: string = 'cluster1',
) => {
  const workloadStatuses = [
    'Pending',
    'Complete',
    'Unknown',
    'Failed',
  ] as const;
  const workloadTypes = [
    'INFERENCE',
    'FINE_TUNING',
    'MODEL_DOWNLOAD',
    'CUSTOM',
  ] as const;
  return Array.from({ length: n }, (_, i) => ({
    id: `metric${i + 1}`,
    projectId: `project${i + 1}`,
    clusterId,
    status: workloadStatuses[i % workloadStatuses.length] as any,
    createdAt: new Date(Date.UTC(2024, 0, 1 + i)).toISOString(),
    createdBy: `user${i + 1}@amd.com`,
    displayName: `Test Workload ${i + 1}`,
    type: workloadTypes[i % workloadTypes.length] as any,
    gpuCount: (i + 1) * 100,
    vram: 10 * (i + 1),
  }));
};

const mockedData = generateClusterWorkloadsMetrics(2);

// Mock project data that matches the workload projectIds
const mockedProjects = [
  {
    id: 'project1',
    name: 'Project 1',
    description: 'Test Project 1',
    status: 'Ready' as const,
    statusReason: null,
    clusterId: 'cluster1',
  },
  {
    id: 'project2',
    name: 'Project 2',
    description: 'Test Project 2',
    status: 'Ready' as const,
    statusReason: null,
    clusterId: 'cluster1',
  },
];

// Mock the API services
vi.mock('@/services/app', () => ({
  deleteWorkload: vi.fn(),
  fetchClusterWorkloadsMetrics: vi.fn(() =>
    Promise.resolve({
      data: mockedData,
      pagination: {
        total: 2,
        page: 1,
        pageSize: 10,
      },
    }),
  ),
  getClusterProjects: vi.fn(() =>
    Promise.resolve({
      data: mockedProjects,
    }),
  ),
}));

const toastSuccessMock = vi.fn();
const toastErrorMock = vi.fn();
vi.mock('@amdenterpriseai/hooks', async (importOriginal) => ({
  ...(await importOriginal()),
  useSystemToast: () => {
    const toast = vi.fn() as any;
    toast.success = toastSuccessMock;
    toast.error = toastErrorMock;
    return { toast };
  },
}));

describe('ClusterWorkloadsTable', () => {
  it('renders component', () => {
    const { container } = render(
      <ClusterWorkloadsTable clusterId={'cluster1'} />,
      {
        wrapper,
      },
    );
    expect(container).toBeTruthy();
    expect(fetchClusterWorkloadsMetrics).toHaveBeenCalledWith('cluster1', {
      page: 1,
      pageSize: 10,
      sort: [
        {
          direction: 'descending',
          field: 'createdAt',
        },
      ],
      filter: [
        {
          fields: ['type'],
          operator: 'eq',
          values: [
            'MODEL_DOWNLOAD',
            'INFERENCE',
            'FINE_TUNING',
            'WORKSPACE',
            'CUSTOM',
          ],
        },
        {
          fields: ['status'],
          operator: 'eq',
          values: [
            'Pending',
            'Running',
            'Complete',
            'Failed',
            'Deleting',
            'DeleteFailed',
            'Unknown',
            'Terminated',
          ],
        },
      ],
    });
    expect(getClusterProjects).toHaveBeenCalledWith('cluster1');
  });

  it('Renders correct name', async () => {
    await act(() => {
      render(<ClusterWorkloadsTable clusterId="cluster1" />, { wrapper });
    });

    await waitFor(() => {
      expect(screen.getByText('Test Workload 1')).toBeInTheDocument();
      expect(screen.queryByText('Test Workload 2')).toBeInTheDocument();
    });
  });

  it('Renders correct user', async () => {
    await act(() => {
      render(<ClusterWorkloadsTable clusterId="cluster1" />, { wrapper });
    });

    await waitFor(() => {
      expect(
        screen.getByText('list.workloads.headers.createdBy.title'),
      ).toBeInTheDocument();
      expect(screen.getByText('user1@amd.com')).toBeInTheDocument();
      expect(screen.getByText('user2@amd.com')).toBeInTheDocument();
    });
  });

  it('Renders correct status', async () => {
    await act(() => {
      render(<ClusterWorkloadsTable clusterId="cluster1" />, { wrapper });
    });
    await waitFor(() => {
      expect(
        screen.getByText('list.workloads.headers.status.title'),
      ).toBeInTheDocument();
      expect(screen.getByText('status.Pending')).toBeInTheDocument();
      expect(screen.getByText('status.Complete')).toBeInTheDocument();
    });
  });

  it('Renders correct gpu count', async () => {
    await act(() => {
      render(<ClusterWorkloadsTable clusterId="cluster1" />, { wrapper });
    });

    await waitFor(() => {
      expect(
        screen.getByText('list.workloads.headers.gpuCount.title'),
      ).toBeInTheDocument();
      expect(screen.getByText('100')).toBeInTheDocument();
      expect(screen.getByText('200')).toBeInTheDocument();
    });
  });

  it('Renders correct vram', async () => {
    await act(() => {
      render(<ClusterWorkloadsTable clusterId="cluster1" />, { wrapper });
    });

    await waitFor(() => {
      expect(
        screen.getByText('list.workloads.headers.vram.title'),
      ).toBeInTheDocument();
      expect(screen.getByText('0.01 GB')).toBeInTheDocument();
      expect(screen.getByText('0.02 GB')).toBeInTheDocument();
    });
  });

  it('Renders correct created time', async () => {
    await act(() => {
      render(<ClusterWorkloadsTable clusterId="cluster1" />, { wrapper });
    });

    await waitFor(() => {
      expect(
        screen.getByText('list.workloads.headers.createdAt.title'),
      ).toBeInTheDocument();

      expect(
        screen.getByText(
          format(new Date(mockedData[0].createdAt), 'yyyy/MM/dd HH:mm'),
        ),
      );
      expect(
        screen.getByText(
          format(new Date(mockedData[1].createdAt), 'yyyy/MM/dd HH:mm'),
        ),
      ).toBeInTheDocument();
    });
  });

  it('Renders correct project names', async () => {
    await act(() => {
      render(<ClusterWorkloadsTable clusterId="cluster1" />, { wrapper });
    });

    await waitFor(() => {
      // Verify project names are displayed (they are rendered as links)
      expect(screen.getByText('Project 1')).toBeInTheDocument();
      expect(screen.getByText('Project 2')).toBeInTheDocument();
    });
  });

  it('Shows a modal and triggers delete for a running workload', async () => {
    const mockedData = generateClusterWorkloadsMetrics(3);

    await act(() => {
      render(<ClusterWorkloadsTable clusterId="cluster1" />, { wrapper });
    });

    await waitFor(() => {
      expect(
        screen.getByText('list.workloads.headers.createdAt.title'),
      ).toBeInTheDocument();

      const dropDowns = screen.getAllByLabelText('list.actions.label');
      expect(dropDowns).toHaveLength(2);
    });

    await act(() => {
      const dropDowns = screen.getAllByLabelText('list.actions.label');

      // Click the dropdown on workload 1
      fireEvent.click(dropDowns[0]);
    });

    const deleteAction = await screen.findByText(
      'list.workloads.actions.delete.title',
    );
    await act(() => {
      fireEvent.click(deleteAction);
    });

    const confirmAction = await screen.findByText('actions.confirm.title');
    await act(() => {
      fireEvent.click(confirmAction);
    });

    await waitFor(() => {
      expect(vi.mocked(deleteWorkload)).toHaveBeenCalled();
      expect(vi.mocked(deleteWorkload).mock.calls[0][0]).toBe('metric1');
    });
  });
});
