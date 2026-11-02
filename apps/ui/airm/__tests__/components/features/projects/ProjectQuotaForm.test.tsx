// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { generateClustersMock } from '@/__mocks__/utils/cluster-mock';
import { generateMockProjectWithMembers } from '@/__mocks__/utils/project-mock';
import ProviderWrapper from '@/__tests__/ProviderWrapper';
import ProjectQuotaForm from '@/components/features/projects/ProjectQuotaForm';
import { ProjectWithMembers } from '@/types/projects';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { QueryClient } from '@tanstack/react-query';
import { updateProject } from '@/services/app';
import { Mock } from 'vitest';

const wrapper = ProviderWrapper;

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

vi.mock('@/services/app', async (importOriginal) => {
  return {
    ...(await importOriginal()),
    updateProject: vi.fn(),
  };
});

function renderWithProjectCache(
  project: ProjectWithMembers,
  cluster: ReturnType<typeof generateClustersMock>[0],
  queryClient: QueryClient,
) {
  queryClient.setQueryData(['project'], project);
  return render(<ProjectQuotaForm project={project} cluster={cluster} />, {
    wrapper: ({ children }) => (
      <ProviderWrapper queryClient={queryClient}>{children}</ProviderWrapper>
    ),
  });
}

describe('ProjectQuotaForm', () => {
  it('should render correctly', () => {
    const { container } = render(
      <ProjectQuotaForm
        project={generateMockProjectWithMembers(1, 1)}
        cluster={generateClustersMock(1)[0]}
      />,
      { wrapper },
    );
    expect(container).toBeInTheDocument();
  });

  it('edit description field calls update project API correctly', async () => {
    const mockProject = generateMockProjectWithMembers(1, 1);
    const mockCluster = generateClustersMock(1)[0];
    mockProject.clusterId = mockCluster.id;

    act(() => {
      render(<ProjectQuotaForm project={mockProject} cluster={mockCluster} />, {
        wrapper,
      });
    });

    const confirmButton = screen.getByText('settings.form.actions.confirm');
    expect(confirmButton).toBeInTheDocument();
    await fireEvent.click(confirmButton);

    await waitFor(() => {
      expect(
        (updateProject as Mock).mock.calls.some((call) =>
          expect
            .objectContaining({
              id: mockProject.id,
            })
            .asymmetricMatch(call[0]),
        ),
      ).toBe(true);
    });
  });

  it('call successful toast when resolved successfully', async () => {
    const mockProject = generateMockProjectWithMembers(1, 1);
    const mockCluster = generateClustersMock(1)[0];
    mockProject.clusterId = mockCluster.id;
    (updateProject as Mock).mockResolvedValue(Promise.resolve());

    act(() => {
      render(<ProjectQuotaForm project={mockProject} cluster={mockCluster} />, {
        wrapper,
      });
    });

    const confirmButton = screen.getByText('settings.form.actions.confirm');
    expect(confirmButton).toBeInTheDocument();
    await fireEvent.click(confirmButton);
    await waitFor(() => {
      expect(updateProject).toHaveBeenCalled();
      expect(toastSuccessMock).toHaveBeenCalled();
    });
  });

  it('call error toast when rejected ', async () => {
    const mockProject = generateMockProjectWithMembers(1, 1);
    const mockCluster = generateClustersMock(1)[0];
    mockProject.clusterId = mockCluster.id;
    (updateProject as Mock).mockResolvedValue(Promise.reject({}));

    act(() => {
      render(<ProjectQuotaForm project={mockProject} cluster={mockCluster} />, {
        wrapper,
      });
    });

    const confirmButton = screen.getByText('settings.form.actions.confirm');
    expect(confirmButton).toBeInTheDocument();
    await fireEvent.click(confirmButton);
    await waitFor(() => {
      expect(updateProject).toHaveBeenCalled();
      expect(toastErrorMock).toHaveBeenCalled();
    });
  });

  it('optimistically updates project quota cache on submit', async () => {
    const mockProject = generateMockProjectWithMembers(1, 1);
    const mockCluster = generateClustersMock(1)[0];
    mockProject.clusterId = mockCluster.id;

    let resolveUpdate!: (value: unknown) => void;
    const updatePromise = new Promise((resolve) => {
      resolveUpdate = resolve;
    });
    (updateProject as Mock).mockReturnValue(updatePromise);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    renderWithProjectCache(mockProject, mockCluster, queryClient);

    await fireEvent.click(screen.getByText('settings.form.actions.confirm'));

    await waitFor(() => {
      expect(updateProject).toHaveBeenCalled();
    });

    const submittedQuota = (updateProject as Mock).mock.calls[0][0].quota;
    const cachedProject = queryClient.getQueryData<ProjectWithMembers>([
      'project',
    ]);

    expect(cachedProject?.quota).toMatchObject(submittedQuota);

    resolveUpdate({});
    await waitFor(() => {
      expect(toastSuccessMock).toHaveBeenCalled();
    });
  });

  it('rolls back project quota cache when submit fails', async () => {
    const mockProject = generateMockProjectWithMembers(1, 1);
    const mockCluster = generateClustersMock(1)[0];
    mockProject.clusterId = mockCluster.id;
    const originalQuota = { ...mockProject.quota };

    (updateProject as Mock).mockRejectedValue(new Error('Save failed'));

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    renderWithProjectCache(mockProject, mockCluster, queryClient);

    await fireEvent.click(screen.getByText('settings.form.actions.confirm'));

    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalled();
    });

    const cachedProject = queryClient.getQueryData<ProjectWithMembers>([
      'project',
    ]);
    expect(cachedProject?.quota).toEqual(originalQuota);
  });

  it('invalidates project and cluster queries on settle', async () => {
    const mockProject = generateMockProjectWithMembers(1, 1);
    const mockCluster = generateClustersMock(1)[0];
    mockProject.clusterId = mockCluster.id;
    (updateProject as Mock).mockResolvedValue({});

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

    renderWithProjectCache(mockProject, mockCluster, queryClient);

    await fireEvent.click(screen.getByText('settings.form.actions.confirm'));

    await waitFor(() => {
      expect(toastSuccessMock).toHaveBeenCalled();
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['project'] });
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['cluster'] });
    });
  });
});
