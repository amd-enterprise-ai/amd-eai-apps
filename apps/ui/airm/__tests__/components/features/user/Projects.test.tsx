// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';

import { addUsersToProject, deleteUserFromProject } from '@/services/app';

import { ClusterStatus } from '@/types/enums/cluster-status';
import { QuotaStatus } from '@/types/enums/quotas';
import { UserRole } from '@amdenterpriseai/types';

import { Projects } from '@/components/features/user';

import { Mock } from 'vitest';

vi.mock('@/services/app', () => ({
  deleteUserFromProject: vi.fn(),
  addUsersToProject: vi.fn(),
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

const queryClient = new QueryClient();

const mockedProjects = [
  {
    name: 'Admin Group',
    id: '123e4567-e89b-12d3-a456-426614174000',
    description: 'Admin Group description',
    clusterId: '456e4567-e89b-12d3-a456-426614174000',
    quota: {
      status: QuotaStatus.READY,
      cpuMilliCores: 1000,
      gpuCount: 1,
      memoryBytes: 2000,
      ephemeralStorageBytes: 10000,
    },
    cluster: {
      id: '456',
      name: 'Test Cluster',
      status: ClusterStatus.HEALTHY,
      lastHeartbeatAt: new Date().toISOString(),
    },
  },
  {
    name: 'Group 2',
    id: '323e4567-e89b-12d3-a456-426614174000',
    description: 'Group 2 description',
    clusterId: '456e4567-e89b-12d3-a456-426614174000',
    quota: {
      status: QuotaStatus.READY,
      cpuMilliCores: 1000,
      gpuCount: 1,
      memoryBytes: 2000,
      ephemeralStorageBytes: 10000,
    },
    cluster: {
      id: '456',
      name: 'Test Cluster',
      status: ClusterStatus.HEALTHY,
      lastHeartbeatAt: new Date().toISOString(),
    },
  },
  {
    name: 'Group 3',
    id: '423e4567-e89b-12d3-a456-426614174000',
    description: 'Group 3 description',
    clusterId: '456e4567-e89b-12d3-a456-426614174000',
    quota: {
      status: QuotaStatus.READY,
      cpuMilliCores: 1000,
      gpuCount: 1,
      memoryBytes: 2000,
      ephemeralStorageBytes: 10000,
    },
    cluster: {
      id: '456',
      name: 'Test Cluster',
      status: ClusterStatus.HEALTHY,
      lastHeartbeatAt: new Date().toISOString(),
    },
  },
];

const renderProjects = (userProjects: any, projects = mockedProjects) => {
  render(
    <QueryClientProvider client={queryClient}>
      <Projects
        user={{
          id: '923e4567-e89b-12d3-a456-426614174000',
          firstName: 'John',
          lastName: 'Doe',
          email: 'john.doe@example.com',
          role: UserRole.PLATFORM_ADMIN,
          projects: userProjects,
        }}
        projects={projects}
      />
    </QueryClientProvider>,
  );
};

describe('Projects', () => {
  const mockDeleteUserFromProject = deleteUserFromProject as Mock;
  const mockAddUsersToProject = addUsersToProject as Mock;

  beforeEach(() => {
    mockDeleteUserFromProject.mockClear();
    toastSuccessMock.mockClear();
    toastErrorMock.mockClear();
  });

  it('renders the component with project name', () => {
    act(() => {
      renderProjects([
        {
          name: 'Admin Group',
          id: '123e4567-e89b-12d3-a456-426614174000',
          description: 'Admin Group description',
        },
      ]);
    });

    expect(
      screen.getByText('detail.projectsAndRoles.projects.title'),
    ).toBeInTheDocument();
    expect(screen.getByText('Admin Group')).toBeInTheDocument();
  });

  it('renders the component without project name', () => {
    act(() => {
      renderProjects([]);
    });

    expect(
      screen.getByText('detail.projectsAndRoles.projects.title'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('detail.projectsAndRoles.projects.empty'),
    ).toBeInTheDocument();
  });

  it('opens the modal when add button is clicked', async () => {
    await act(async () => {
      renderProjects([
        {
          name: 'Admin Group',
          id: '123e4567-e89b-12d3-a456-426614174000',
          description: 'Admin Group description',
        },
      ]);
    });

    const addButton = screen.getByLabelText(
      'detail.projectsAndRoles.projects.actions.add.title',
    );

    fireEvent.click(addButton);

    const modalTitle = screen.queryAllByText(
      'detail.projectsAndRoles.projects.actions.add.title',
    );
    expect(modalTitle[0]).toBeInTheDocument();
  });

  it('opens the delete confirmation modal when delete button is clicked', async () => {
    await act(async () => {
      renderProjects([
        {
          name: 'Admin Group',
          id: '123e4567-e89b-12d3-a456-426614174000',
          description: 'Admin Group description',
        },
      ]);
    });

    const deleteButton = screen.getByLabelText(
      'detail.projectsAndRoles.projects.actions.delete.title',
    );
    fireEvent.click(deleteButton);

    const deleteModalTitle = screen.queryAllByText(
      'detail.projectsAndRoles.projects.actions.delete.title',
    );
    expect(deleteModalTitle[0]).toBeInTheDocument();
  });

  it('calls deleteUserFromProjectAPI when delete confirmation modal is confirmed', async () => {
    await act(async () => {
      renderProjects([
        {
          name: 'Admin Group',
          id: '123e4567-e89b-12d3-a456-426614174000',
          description: 'Admin Group description',
        },
      ]);
    });

    const deleteButton = screen.getByLabelText(
      'detail.projectsAndRoles.projects.actions.delete.title',
    );
    fireEvent.click(deleteButton);

    const confirmButton = screen.getByText('actions.confirm.title');
    fireEvent.click(confirmButton);

    await waitFor(() => {
      expect(deleteUserFromProject).toHaveBeenCalledWith(
        {
          projectId: '123e4567-e89b-12d3-a456-426614174000',
          userId: '923e4567-e89b-12d3-a456-426614174000',
        },
        expect.any(Object),
      );
      expect(toastSuccessMock).toHaveBeenCalledWith(
        'detail.projectsAndRoles.projects.notification.delete.success',
      );
    });
  });

  it('invalidates queries on successful delete', async () => {
    const invalidateQueriesSpy = vi.spyOn(queryClient, 'invalidateQueries');

    mockDeleteUserFromProject.mockImplementation(() => Promise.resolve());

    await act(async () => {
      renderProjects([
        {
          name: 'Admin Group',
          id: '123e4567-e89b-12d3-a456-426614174000',
          description: 'Admin Group description',
        },
      ]);
    });

    const deleteButton = screen.getByLabelText(
      'detail.projectsAndRoles.projects.actions.delete.title',
    );
    fireEvent.click(deleteButton);

    const confirmButton = screen.getByText('actions.confirm.title');
    fireEvent.click(confirmButton);

    await waitFor(() => {
      expect(deleteUserFromProject).toHaveBeenCalledWith(
        {
          projectId: '123e4567-e89b-12d3-a456-426614174000',
          userId: '923e4567-e89b-12d3-a456-426614174000',
        },
        expect.any(Object),
      );
      expect(invalidateQueriesSpy).toHaveBeenCalledWith({ queryKey: ['user'] });
    });

    invalidateQueriesSpy.mockRestore();
  });

  it('disables the select if there are no other projects available', () => {
    renderProjects(
      [
        {
          name: 'Admin Group',
          id: '123e4567-e89b-12d3-a456-426614174000',
          description: 'Admin Group description',
        },
      ],
      [mockedProjects[0]],
    );

    const addButton = screen.getByLabelText(
      'detail.projectsAndRoles.projects.actions.add.title',
    ) as HTMLInputElement;

    expect(addButton.disabled).toBeTruthy();
  });

  it('populates the Select component with the correct fields in ModalForm', async () => {
    await act(async () => {
      renderProjects([
        {
          name: 'Admin Group',
          id: '123e4567-e89b-12d3-a456-426614174000',
          description: 'Admin Group description',
        },
      ]);
    });

    const addButton = screen.getByLabelText(
      'detail.projectsAndRoles.projects.actions.add.title',
    );

    fireEvent.click(addButton);

    const modalTitle = screen.queryAllByText(
      'detail.projectsAndRoles.projects.actions.add.title',
    );
    expect(modalTitle[0]).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(
        screen.getByRole('button', {
          name: /detail.projectsAndRoles.projects.form.project.label/,
        }),
      );
    });

    expect(screen.getByRole('option', { name: 'Group 2' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Group 3' })).toBeInTheDocument();
    expect(
      screen.queryByRole('option', { name: 'Admin Group' }),
    ).not.toBeInTheDocument();
  });

  it('calls addUsersToProjectAPI with the correct value when the third option is selected and confirmed', async () => {
    await act(async () => {
      renderProjects([
        {
          name: 'Admin Group',
          id: '123e4567-e89b-12d3-a456-426614174000',
          description: 'Admin Group description',
        },
      ]);
    });

    const addButton = screen.getByLabelText(
      'detail.projectsAndRoles.projects.actions.add.title',
    );

    fireEvent.click(addButton);

    await act(async () => {
      fireEvent.click(
        screen.getByRole('button', {
          name: /detail.projectsAndRoles.projects.form.project.label/,
        }),
      );
    });

    fireEvent.click(screen.getByRole('option', { name: 'Group 3' }));

    const confirmButton = screen.getByText(
      'detail.projectsAndRoles.projects.actions.add.confirm',
    );
    fireEvent.click(confirmButton);

    await waitFor(() => {
      expect(mockAddUsersToProject).toHaveBeenCalledWith(
        {
          projectId: '423e4567-e89b-12d3-a456-426614174000',
          userIds: ['923e4567-e89b-12d3-a456-426614174000'],
        },
        expect.any(Object),
      );
    });
  });

  it('invalidates queries on successful add', async () => {
    const invalidateQueriesSpy = vi.spyOn(queryClient, 'invalidateQueries');

    mockAddUsersToProject.mockImplementation(() => Promise.resolve());

    await act(async () => {
      renderProjects([
        {
          name: 'Admin Group',
          id: '123e4567-e89b-12d3-a456-426614174000',
          description: 'Admin Group description',
        },
      ]);
    });

    const addButton = screen.getByLabelText(
      'detail.projectsAndRoles.projects.actions.add.title',
    );

    fireEvent.click(addButton);

    await act(async () => {
      fireEvent.click(
        screen.getByRole('button', {
          name: /detail.projectsAndRoles.projects.form.project.label/,
        }),
      );
    });

    fireEvent.click(screen.getByRole('option', { name: 'Group 3' }));

    const confirmButton = screen.getByText(
      'detail.projectsAndRoles.projects.actions.add.confirm',
    );
    fireEvent.click(confirmButton);

    await waitFor(() => {
      expect(mockAddUsersToProject).toHaveBeenCalledWith(
        {
          projectId: '423e4567-e89b-12d3-a456-426614174000',
          userIds: ['923e4567-e89b-12d3-a456-426614174000'],
        },
        expect.any(Object),
      );
      expect(invalidateQueriesSpy).toHaveBeenCalledWith({ queryKey: ['user'] });
    });

    invalidateQueriesSpy.mockRestore();

    expect(toastSuccessMock).toHaveBeenCalledWith(
      'detail.projectsAndRoles.projects.notification.add.success',
    );
  });
});
