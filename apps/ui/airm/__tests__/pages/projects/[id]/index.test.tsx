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
  fetchProjectAverageGPUIdleTime,
  fetchProjectAverageWaitTime,
  fetchProjectGPUDeviceUtilization,
  fetchProjectGPUMemoryUtilization,
  fetchProjectWorkloadsStatuses,
  fetchProjectWorkloadsMetrics,
  deleteProject,
} from '@/services/app';
import { useAccessControl } from '@/hooks/useAccessControl';

import { ClusterStatus } from '@/types/enums/cluster-status';
import { ProjectStatus } from '@/types/enums/projects';
import { QuotaStatus } from '@/types/enums/quotas';
import { GPU_PREEMPTION_DISABLED, ProjectWithMembers } from '@/types/projects';

import ProjectPage from '@/pages/projects/[id]';

import wrapper from '@/__tests__/ProviderWrapper';
import '@testing-library/jest-dom';
import { Mock } from 'vitest';

const generateMockProjects = (count: number): ProjectWithMembers[] => {
  return Array.from({ length: count }, (_, i) => ({
    id: (i + 1).toString(),
    clusterId: '1',
    name: `Name ${i + 1}`,
    description: `Description ${i + 1}`,
    status: ProjectStatus.READY,
    statusReason: null,
    quota: {
      status: QuotaStatus.READY,
      cpuMilliCores: 1000,
      gpuCount: 1,
      memoryBytes: 2000,
      ephemeralStorageBytes: 10000,
    },
    cluster: {
      id: '1',
      name: `Cluster ${i + 1}`,
      lastHeartbeatAt: new Date().toISOString(),
      status: ClusterStatus.HEALTHY,
    },
    users: [],
    invitedUsers: [],
    gpuPreemption: GPU_PREEMPTION_DISABLED,
  }));
};

vi.mock('@/services/app', async (importOriginal) => {
  return {
    ...(await importOriginal()),
    fetchProjectGPUDeviceUtilization: vi.fn(),
    fetchProjectGPUMemoryUtilization: vi.fn(),
    fetchProjectWorkloadsStatuses: vi.fn(),
    fetchProjectWorkloadsMetrics: vi.fn(),
    fetchProjectAverageWaitTime: vi.fn(),
    fetchProjectAverageGPUIdleTime: vi.fn(),
    fetchProjectSecrets: vi.fn(),
    fetchProjectStorages: vi.fn(),
    deleteProject: vi.fn(),
  };
});

const mockPush = vi.fn();

vi.mock('next/router', () => ({
  useRouter: () => ({
    query: { id: '1' },
    push: mockPush,
  }),
}));

vi.mock('@/hooks/useAccessControl', () => ({
  useAccessControl: vi.fn(),
}));

const adminAccessControl = {
  isRoleManagementEnabled: true,
  isInviteEnabled: true,
  isAdministrator: true,
  smtpEnabled: true,
  isTempPasswordRequired: false,
};

describe('projects page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAccessControl).mockReturnValue(adminAccessControl);
  });

  const renderProjectPage = (
    props?: Partial<React.ComponentProps<typeof ProjectPage>>,
  ) => {
    return render(
      <ProjectPage
        project={props?.project ?? generateMockProjects(1)[0]}
        {...props}
      />,
      { wrapper },
    );
  };

  it('should not crash the page', () => {
    const { container } = renderProjectPage({
      project: generateMockProjects(1)[0],
    });
    expect(container).toBeTruthy();
    expect(screen.getByText('dashboard.overview.title')).toBeInTheDocument();
  });

  it('fetchProjectGPUDeviceUtilization the page', () => {
    act(() => {
      renderProjectPage({
        project: generateMockProjects(1)[0],
      });
    });

    expect(fetchProjectGPUDeviceUtilization as Mock).toHaveBeenCalled();
  });

  it('fetchProjectWorkloadsMetrics the page', () => {
    act(() => {
      renderProjectPage({
        project: generateMockProjects(1)[0],
      });
    });

    expect(fetchProjectWorkloadsMetrics as Mock).toHaveBeenCalled();
  });

  it('fetchProjectWorkloadsStatuses the page', () => {
    act(() => {
      renderProjectPage({
        project: generateMockProjects(1)[0],
      });
    });

    expect(fetchProjectWorkloadsStatuses as Mock).toHaveBeenCalled();
  });

  it('fetchProjectGPUMemoryUtilization the page', () => {
    act(() => {
      renderProjectPage({
        project: generateMockProjects(1)[0],
      });
    });

    expect(fetchProjectGPUMemoryUtilization as Mock).toHaveBeenCalled();
  });

  it('fetchProjectGPUDeviceUtilization the page', () => {
    act(() => {
      renderProjectPage({
        project: generateMockProjects(1)[0],
      });
    });

    expect(fetchProjectGPUDeviceUtilization as Mock).toHaveBeenCalled();
  });

  it('fetchProjectAverageWaitTime the page', () => {
    act(() => {
      renderProjectPage({
        project: generateMockProjects(1)[0],
      });
    });

    expect(fetchProjectAverageWaitTime as Mock).toHaveBeenCalled();
  });

  it('fetchProjectGPUIdleTime the page', () => {
    act(() => {
      renderProjectPage({
        project: generateMockProjects(1)[0],
      });
    });

    expect(fetchProjectAverageGPUIdleTime as Mock).toHaveBeenCalled();
  });

  it('refresh button trigger refetch', async () => {
    await act(() => {
      renderProjectPage({
        project: generateMockProjects(1)[0],
      });
    });

    expect(fetchProjectGPUMemoryUtilization as Mock).toBeCalledTimes(1);
    expect(fetchProjectGPUDeviceUtilization as Mock).toBeCalledTimes(1);
    expect(fetchProjectAverageWaitTime as Mock).toBeCalledTimes(1);
    expect(fetchProjectAverageGPUIdleTime as Mock).toBeCalledTimes(1);

    await waitFor(() => {
      expect(screen.getByText('actions.refresh.title')).toBeInTheDocument();
    });

    await act(() => {
      fireEvent.click(screen.getByText('actions.refresh.title'));
    });

    expect(fetchProjectGPUMemoryUtilization as Mock).toBeCalledTimes(2);
    expect(fetchProjectGPUDeviceUtilization as Mock).toBeCalledTimes(2);
  });

  it('should navigate to project settings when edit settings is clicked from dropdown', async () => {
    await act(async () => {
      renderProjectPage({
        project: generateMockProjects(1)[0],
      });
    });

    const actionsButton = screen.getByText('dashboard.action.label');
    await act(async () => {
      fireEvent.click(actionsButton);
    });

    const editSettingsItem = screen.getByText('dashboard.action.editSettings');
    await act(async () => {
      fireEvent.click(editSettingsItem);
    });

    expect(mockPush).toHaveBeenCalledWith('/projects/1/edit');
  });

  it('should handle time range change correctly', async () => {
    await act(() => {
      renderProjectPage({
        project: generateMockProjects(1)[0],
      });
    });

    await waitFor(() => {
      expect(screen.getByText('actions.refresh.title')).toBeInTheDocument();
    });
  });

  it('should render all dashboard sections', () => {
    act(() => {
      renderProjectPage({
        project: generateMockProjects(1)[0],
      });
    });

    expect(screen.getByText('dashboard.overview.title')).toBeInTheDocument();
    expect(screen.getByText('dashboard.workloads.title')).toBeInTheDocument();
  });

  it('should render dropdown menu with all action items', async () => {
    const projectWithWorkbench = {
      ...generateMockProjects(1)[0],
      cluster: {
        ...generateMockProjects(1)[0].cluster,
        workbenchBaseUrl: 'https://workbench.example.com',
      },
    };

    await act(async () => {
      renderProjectPage({ project: projectWithWorkbench });
    });

    const actionsButton = screen.getByText('dashboard.action.label');
    await act(async () => {
      fireEvent.click(actionsButton);
    });

    expect(
      screen.getByText('dashboard.action.editSettings'),
    ).toBeInTheDocument();
    expect(screen.getByText('dashboard.action.viewInAiwb')).toBeInTheDocument();
    expect(screen.getByText('dashboard.action.delete')).toBeInTheDocument();
  });

  it('should open workbench URL in new window when viewInAiwb is clicked', async () => {
    const windowOpenSpy = vi
      .spyOn(window, 'open')
      .mockImplementation(() => null);
    const projectWithWorkbench = {
      ...generateMockProjects(1)[0],
      cluster: {
        ...generateMockProjects(1)[0].cluster,
        workbenchBaseUrl: 'https://workbench.example.com',
      },
    };

    await act(async () => {
      renderProjectPage({ project: projectWithWorkbench });
    });

    const actionsButton = screen.getByText('dashboard.action.label');
    await act(async () => {
      fireEvent.click(actionsButton);
    });

    const viewInAiwbItem = screen.getByText('dashboard.action.viewInAiwb');
    await act(async () => {
      fireEvent.click(viewInAiwbItem);
    });

    expect(windowOpenSpy).toHaveBeenCalledWith(
      `https://workbench.example.com/${projectWithWorkbench.name}`,
      '_blank',
      'noopener,noreferrer',
    );

    windowOpenSpy.mockRestore();
  });

  it('should strip trailing slashes from workbench URL to avoid double-slash', async () => {
    const windowOpenSpy = vi
      .spyOn(window, 'open')
      .mockImplementation(() => null);
    const projectWithTrailingSlash = {
      ...generateMockProjects(1)[0],
      cluster: {
        ...generateMockProjects(1)[0].cluster,
        workbenchBaseUrl: 'https://workbench.example.com/',
      },
    };

    await act(async () => {
      renderProjectPage({ project: projectWithTrailingSlash });
    });

    const actionsButton = screen.getByText('dashboard.action.label');
    await act(async () => {
      fireEvent.click(actionsButton);
    });

    const viewInAiwbItem = screen.getByText('dashboard.action.viewInAiwb');
    await act(async () => {
      fireEvent.click(viewInAiwbItem);
    });

    expect(windowOpenSpy).toHaveBeenCalledWith(
      `https://workbench.example.com/${projectWithTrailingSlash.name}`,
      '_blank',
      'noopener,noreferrer',
    );

    windowOpenSpy.mockRestore();
  });

  it('should show viewInAiwb as disabled when workbenchBaseUrl has invalid scheme', async () => {
    const projectWithInvalidUrl = {
      ...generateMockProjects(1)[0],
      cluster: {
        ...generateMockProjects(1)[0].cluster,
        workbenchBaseUrl: 'ftp://invalid.example.com',
      },
    };

    await act(async () => {
      renderProjectPage({ project: projectWithInvalidUrl });
    });

    const actionsButton = screen.getByText('dashboard.action.label');
    await act(async () => {
      fireEvent.click(actionsButton);
    });

    await waitFor(() => {
      const viewInAiwbItem = screen.getByText('dashboard.action.viewInAiwb');
      expect(
        viewInAiwbItem.closest('[data-disabled="true"]'),
      ).toBeInTheDocument();
    });
  });

  it('should show delete confirmation modal when delete is clicked', async () => {
    await act(async () => {
      renderProjectPage({
        project: generateMockProjects(1)[0],
      });
    });

    const actionsButton = screen.getByText('dashboard.action.label');
    await act(async () => {
      fireEvent.click(actionsButton);
    });

    const deleteItem = screen.getByText('dashboard.action.delete');
    await act(async () => {
      fireEvent.click(deleteItem);
    });

    await waitFor(() => {
      expect(
        screen.getByText('settings.delete.confirmation.title'),
      ).toBeInTheDocument();
    });
  });

  it('should call deleteProject API when delete is confirmed', async () => {
    await act(async () => {
      renderProjectPage({
        project: generateMockProjects(1)[0],
      });
    });

    const actionsButton = screen.getByText('dashboard.action.label');
    await act(async () => {
      fireEvent.click(actionsButton);
    });

    const deleteItem = screen.getByText('dashboard.action.delete');
    await act(async () => {
      fireEvent.click(deleteItem);
    });

    await waitFor(() => {
      expect(
        screen.getByText('settings.delete.confirmation.title'),
      ).toBeInTheDocument();
    });

    const confirmButton = screen.getByText('actions.confirm.title');
    await act(async () => {
      fireEvent.click(confirmButton);
    });

    await waitFor(() => {
      expect(vi.mocked(deleteProject)).toHaveBeenCalledWith(
        '1',
        expect.any(Object),
      );
    });
  });
});

describe('projects page - non-admin', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAccessControl).mockReturnValue({
      ...adminAccessControl,
      isAdministrator: false,
    });
  });

  const renderProjectPage = (
    props?: Partial<React.ComponentProps<typeof ProjectPage>>,
  ) => {
    return render(
      <ProjectPage
        project={props?.project ?? generateMockProjects(1)[0]}
        {...props}
      />,
      { wrapper },
    );
  };

  it('should show team member alert for non-administrators', async () => {
    await act(async () => {
      renderProjectPage({
        project: generateMockProjects(1)[0],
      });
    });

    const actionsButton = screen.getByText('dashboard.action.label');
    await act(async () => {
      fireEvent.click(actionsButton);
    });

    expect(
      screen.getByText('dashboard.action.teamMemberAlert.title'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('dashboard.action.teamMemberAlert.description'),
    ).toBeInTheDocument();
  });

  it('should disable delete action for non-administrators', async () => {
    await act(async () => {
      renderProjectPage({
        project: generateMockProjects(1)[0],
      });
    });

    const actionsButton = screen.getByText('dashboard.action.label');
    await act(async () => {
      fireEvent.click(actionsButton);
    });

    const deleteItem = screen.getByText('dashboard.action.delete');
    expect(deleteItem.closest('[data-disabled="true"]')).toBeInTheDocument();
  });
});
