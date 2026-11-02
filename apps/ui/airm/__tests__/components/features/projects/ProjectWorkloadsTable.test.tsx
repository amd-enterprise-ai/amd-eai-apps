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

import { fetchProjectWorkloadsMetrics } from '@/services/app';
import { deleteWorkload } from '@/services/app';

import { ProjectWorkloadsTable } from '@/components/features/projects';

import wrapper from '@/__tests__/ProviderWrapper';

const generateProjectWorkloadsMetrics = (
  n: number,
  projectId: string = 'project1',
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
    projectId,
    clusterId: `cluster${i + 1}`,
    status: workloadStatuses[i % workloadStatuses.length] as any,
    createdAt: new Date(Date.UTC(2024, 0, 1 + i)).toISOString(),
    createdBy: `user${i + 1}@amd.com`,
    displayName: `Test Workload ${i + 1}`,
    type: workloadTypes[i % workloadTypes.length] as any,
    gpuCount: (i + 1) * 100,
    vram: 10 * (i + 1),
    runTime: 10 * (i + 1),
  }));
};

const mockedData = generateProjectWorkloadsMetrics(2);

// Mock the API services
vi.mock('@/services/app', () => ({
  deleteWorkload: vi.fn(),
  fetchProjectWorkloadsMetrics: vi.fn(() =>
    Promise.resolve({
      data: mockedData,
      pagination: {
        total: 2,
        page: 1,
        pageSize: 10,
      },
    }),
  ),
}));

vi.mock('@amdenterpriseai/services/app', () => ({
  deleteWorkload: vi.fn(),
  fetchSubmittableProjects: vi.fn(() =>
    Promise.resolve({
      projects: [
        { id: 'project1', name: 'Project 1' },
        { id: 'project2', name: 'Project 2' },
      ],
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

describe('ProjectWorkloadsTable', () => {
  it('renders component', () => {
    const { container } = render(
      <ProjectWorkloadsTable projectId={'project1'} />,
      {
        wrapper,
      },
    );
    expect(container).toBeTruthy();
    expect(fetchProjectWorkloadsMetrics).toHaveBeenCalledWith('project1', {
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
  });

  it('Renders correct name', async () => {
    await act(() => {
      render(<ProjectWorkloadsTable projectId="project1" />, { wrapper });
    });

    await waitFor(() => {
      expect(screen.getByText('Test Workload 1')).toBeInTheDocument();
      expect(screen.queryByText('Test Workload 2')).toBeInTheDocument();
    });
  });

  it('Renders correct user', async () => {
    await act(() => {
      render(<ProjectWorkloadsTable projectId="project1" />, { wrapper });
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
      render(<ProjectWorkloadsTable projectId="projectId1" />, { wrapper });
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
      render(<ProjectWorkloadsTable projectId="project1" />, { wrapper });
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
      render(<ProjectWorkloadsTable projectId="project1" />, { wrapper });
    });

    await waitFor(() => {
      expect(
        screen.getByText('list.workloads.headers.vram.title'),
      ).toBeInTheDocument();
      expect(screen.getByText('0.01 GB')).toBeInTheDocument();
      expect(screen.getByText('0.02 GB')).toBeInTheDocument();
    });
  });

  it('Renders correct run time in seconds', async () => {
    await act(() => {
      render(<ProjectWorkloadsTable projectId="project1" />, { wrapper });
    });
    await waitFor(() => {
      expect(
        screen.getByText('list.workloads.headers.runTime.title'),
      ).toBeInTheDocument();
      expect(screen.getByText('10s')).toBeInTheDocument();
      expect(screen.getByText('20s')).toBeInTheDocument();
    });
  });

  it('Renders correct created time', async () => {
    await act(() => {
      render(<ProjectWorkloadsTable projectId="project1" />, { wrapper });
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

  it('Shows a modal and triggers delete for a running workload', async () => {
    const mockedData = generateProjectWorkloadsMetrics(3);

    await act(() => {
      render(<ProjectWorkloadsTable projectId="123" />, { wrapper });
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

    // Click the delete button
    await fireEvent.click(
      screen.getByText('list.workloads.actions.delete.title'),
    );

    // Confirm the deletion
    await fireEvent.click(screen.getByText('actions.confirm.title'));

    await waitFor(() => {
      expect(vi.mocked(deleteWorkload)).toHaveBeenCalledWith(
        'metric1',
        expect.any(Object),
      );
    });
  });

  it('renders custom row action items if they are passed as props', async () => {
    const customActionMock = vi.fn();
    const customRowActions = () => [
      {
        key: 'custom',
        label: 'Custom Action',
        onPress: customActionMock,
      },
    ];

    await act(() => {
      render(
        <ProjectWorkloadsTable
          projectId="project1"
          rowActions={customRowActions}
        />,
        { wrapper },
      );
    });

    await waitFor(() => {
      expect(
        screen.getByText('list.workloads.headers.createdAt.title'),
      ).toBeInTheDocument();
    });

    const dropDowns = screen.getAllByLabelText('list.actions.label');
    expect(dropDowns).toHaveLength(2);

    await act(() => {
      fireEvent.click(dropDowns[0]);
    });

    const customActionButton = screen.getByText('Custom Action');
    expect(customActionButton).toBeInTheDocument();

    expect(
      screen.queryByText('list.workloads.actions.delete.title'),
    ).not.toBeInTheDocument();

    await act(async () => {
      await fireEvent.click(customActionButton);
    });

    expect(customActionMock).toHaveBeenCalled();
  });
});
