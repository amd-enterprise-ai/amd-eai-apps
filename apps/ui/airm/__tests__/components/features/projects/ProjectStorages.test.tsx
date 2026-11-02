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

import { generateMockProjects } from '@/__mocks__/utils/project-mock';
import {
  generateMockProjectStoragesWithParentStorage,
  generateMockStorages,
} from '@/__mocks__/utils/storages-mock';

import { ProjectStatus } from '@/types/enums/projects';
import { ProjectStorageStatus } from '@/types/enums/storages';
import { ProjectWithMembers } from '@/types/projects';

import { ProjectStorages } from '@/components/features/projects';

import wrapper from '@/__tests__/ProviderWrapper';
import { cloneDeep } from 'lodash';
import { DEFAULT_REFETCH_INTERVAL_FOR_PENDING_DATA } from '@amdenterpriseai/utils/app';
import { fetchProjectStorages } from '@/services/app';

vi.mock('@/services/app', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/app')>()),
  fetchProjectSecrets: vi.fn(),
  fetchProjectStorages: vi.fn(),
}));

vi.mock('@amdenterpriseai/hooks', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@amdenterpriseai/hooks')>()),
  useAccessControl: () => ({
    isRoleManagementEnabled: true,
    isInviteEnabled: true,
    isAdministrator: true,
    smtpEnabled: true,
    isTempPasswordRequired: false,
  }),
}));

describe('ProjectStorages', () => {
  const projectStorages = generateMockProjectStoragesWithParentStorage(1);
  const storages = generateMockStorages(1);

  const baseProject = generateMockProjects(1)[0];
  const project: ProjectWithMembers = {
    ...baseProject,
    users: [],
    invitedUsers: [],
  };

  const setup = (
    props?: Partial<React.ComponentProps<typeof ProjectStorages>>,
  ) => {
    const onOpenChange = vi.fn();
    act(() => {
      render(
        <ProjectStorages
          storages={storages}
          projectStorages={projectStorages}
          project={project}
          {...props}
        />,
        { wrapper },
      );
    });
    return { onOpenChange };
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('render without crashing', () => {
    setup();
    expect(screen.getByText('list.headers.name.title')).toBeInTheDocument();
    expect(screen.getByText('list.headers.type.title')).toBeInTheDocument();
    expect(screen.getByText('list.headers.status.title')).toBeInTheDocument();
    expect(
      screen.getByText('list.headers.createdAt.title'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('list.headers.createdBy.title'),
    ).toBeInTheDocument();
    expect(fetchProjectStorages).toHaveBeenCalled();

    expect(screen.getByText('actions.assignStorage.label')).toBeInTheDocument();
  });

  it('render with disabled button if project is not ready', () => {
    setup({ project: { ...project, status: ProjectStatus.PENDING } });
    expect(
      screen.getByRole('button', { name: 'actions.assignStorage.label' }),
    ).toBeDisabled();
  });

  it('render assign button not disabled if project is ready', () => {
    setup({ project: { ...project, status: ProjectStatus.READY } });
    expect(
      screen.getByRole('button', { name: 'actions.assignStorage.label' }),
    ).not.toBeDisabled();
  });

  it('render delete row action to be not disabled when in synced state', () => {
    const mockStorages = generateMockStorages(1);
    const mockProjectId = 'mock-project-id';
    const mockProject = {
      ...project,
      status: ProjectStatus.READY,
      id: mockProjectId,
    };
    const mockProjectStorages = generateMockProjectStoragesWithParentStorage(
      1,
      mockProjectId,
    );

    mockProjectStorages[0].status = ProjectStorageStatus.SYNCED;
    mockStorages[0].projectStorages = mockProjectStorages;

    setup({
      project: mockProject,
      storages: mockStorages,
      projectStorages: mockProjectStorages,
    });
    const actionButton = screen.getByRole('button', {
      name: 'list.actions.label',
    });
    expect(actionButton).toBeInTheDocument();

    fireEvent.click(actionButton);

    const deleteAction = screen.getByRole('menuitem', {
      name: 'list.actions.deleteFromProject.label',
    });
    expect(deleteAction).toBeInTheDocument();
    expect(deleteAction).not.toHaveAttribute('data-disabled');
  });

  it('render delete row action to be disabled when in deleting state', () => {
    const mockStorages = generateMockStorages(1);
    const mockProjectId = 'mock-project-id';
    const mockProject = {
      ...project,
      status: ProjectStatus.READY,
      id: mockProjectId,
    };
    const mockProjectStorages = generateMockProjectStoragesWithParentStorage(
      1,
      mockProjectId,
    );

    mockProjectStorages[0].status = ProjectStorageStatus.DELETING;
    mockStorages[0].projectStorages = mockProjectStorages;

    setup({
      project: mockProject,
      storages: mockStorages,
      projectStorages: mockProjectStorages,
    });
    const actionButton = screen.getByRole('button', {
      name: 'list.actions.label',
    });
    expect(actionButton).toBeInTheDocument();

    fireEvent.click(actionButton);

    const deleteAction = screen.getByRole('menuitem', {
      name: 'list.actions.deleteFromProject.label',
    });
    expect(deleteAction).toBeInTheDocument();
    expect(deleteAction).toHaveAttribute('data-disabled', 'true');
  });

  it('delete button shows storage delete confirm modal', () => {
    const mockStorages = generateMockStorages(1);
    const mockProjectId = 'mock-project-id';
    const mockProject = {
      ...project,
      status: ProjectStatus.READY,
      id: mockProjectId,
    };
    const mockProjectStorages = generateMockProjectStoragesWithParentStorage(
      1,
      mockProjectId,
    );
    mockProjectStorages[0].status = ProjectStorageStatus.SYNCED;
    mockStorages[0].projectStorages = mockProjectStorages;

    setup({
      project: mockProject,
      storages: mockStorages,
      projectStorages: mockProjectStorages,
    });
    const actionButton = screen.getByRole('button', {
      name: 'list.actions.label',
    });
    expect(actionButton).toBeInTheDocument();

    fireEvent.click(actionButton);

    const deleteAction = screen.getByRole('menuitem', {
      name: 'list.actions.deleteFromProject.label',
    });
    expect(deleteAction).toBeInTheDocument();
    act(() => {
      fireEvent.click(deleteAction);
    });

    expect(
      screen.getByText('form.deleteProjectStorage.title'),
    ).toBeInTheDocument();
  });

  it('filter will return correct storages', async () => {
    const mockStorages = generateMockStorages(2);
    const mockProjectId = 'mock-project-id';
    const mockProjectStorages = generateMockProjectStoragesWithParentStorage(
      1,
      mockProjectId,
    );
    mockProjectStorages[0].status = ProjectStorageStatus.SYNCED;
    mockStorages[0].projectStorages = mockProjectStorages;
    const mockProject = {
      ...project,
      status: ProjectStatus.READY,
      id: mockProjectId,
    };

    await setup({
      project: mockProject,
      storages: mockStorages,
      projectStorages: mockProjectStorages,
    });
    const filterInput = screen.getByLabelText('list.filter.search.label');
    expect(filterInput).toBeInTheDocument();

    await act(() => {
      fireEvent.change(filterInput, { target: { value: 'none' } });
    });

    await waitFor(() => {
      expect(screen.getByText('list.empty.description')).toBeInTheDocument();
    });
  });

  it('calls onRefresh when refresh button is clicked', async () => {
    setup();

    expect(fetchProjectStorages).toBeCalledTimes(1);
    act(() => {
      fireEvent.click(
        screen.getByRole('button', {
          name: 'actions.refresh.title',
        }),
      );
    });

    expect(fetchProjectStorages).toBeCalledTimes(2);
  });

  it('refetches the data if project storage is pending', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });

    const mockStorages = generateMockStorages(1);
    const mockProjectId = 'mock-project-id';
    const mockProject = {
      ...project,
      status: ProjectStatus.READY,
      id: mockProjectId,
    };
    const mockProjectStorages = generateMockProjectStoragesWithParentStorage(
      1,
      mockProjectId,
    );
    mockProjectStorages[0].status = ProjectStorageStatus.PENDING;
    mockStorages[0].projectStorages = mockProjectStorages;

    // Immediately after page load
    vi.mocked(fetchProjectStorages).mockResolvedValueOnce({
      data: mockProjectStorages,
    });

    let syncedProjectStorages = cloneDeep(mockProjectStorages);
    syncedProjectStorages[0].status = ProjectStorageStatus.SYNCED;
    // After 10 seconds, synced
    vi.mocked(fetchProjectStorages).mockResolvedValueOnce({
      data: syncedProjectStorages,
    });

    setup({
      project: mockProject,
      storages: mockStorages,
      projectStorages: mockProjectStorages,
    });

    // On page load
    expect(fetchProjectStorages).toBeCalledTimes(1);

    // After 10 seconds, synced storages
    await act(() =>
      vi.advanceTimersByTimeAsync(DEFAULT_REFETCH_INTERVAL_FOR_PENDING_DATA),
    );
    expect(fetchProjectStorages).toBeCalledTimes(2);

    // No more polling
    await act(() =>
      vi.advanceTimersByTimeAsync(DEFAULT_REFETCH_INTERVAL_FOR_PENDING_DATA),
    );
    expect(fetchProjectStorages).toBeCalledTimes(2);

    vi.useRealTimers();
  });

  it('opens assign storage drawer when assign button dropdown option is clicked', () => {
    setup({ project: { ...project, status: ProjectStatus.READY } });

    const assignButton = screen.getByRole('button', {
      name: 'actions.assignStorage.label',
    });

    // Click to open dropdown
    fireEvent.click(assignButton);

    // Click the S3 option in the dropdown
    const s3Option = screen.getByRole('menuitem', {
      name: 'actions.assignStorage.options.S3.label',
    });
    fireEvent.click(s3Option);

    // AssignStorageToProject drawer should be opened
    expect(screen.getByText('form.assignToProject.title')).toBeInTheDocument();
  });

  it('calculates existing storage ids correctly', () => {
    const mockStorages = generateMockStorages(3);
    const mockProjectId = 'mock-project-id';
    const mockProject = {
      ...project,
      status: ProjectStatus.READY,
      id: mockProjectId,
    };
    const mockProjectStorages = generateMockProjectStoragesWithParentStorage(
      2,
      mockProjectId,
    );

    setup({
      project: mockProject,
      storages: mockStorages,
      projectStorages: mockProjectStorages,
    });

    // Click assign button to open dropdown
    const assignButton = screen.getByRole('button', {
      name: 'actions.assignStorage.label',
    });
    fireEvent.click(assignButton);

    // Click the S3 option in the dropdown
    const s3Option = screen.getByRole('menuitem', {
      name: 'actions.assignStorage.options.S3.label',
    });
    fireEvent.click(s3Option);

    // Should filter out already assigned storages
    expect(screen.getByText('form.assignToProject.title')).toBeInTheDocument();
  });
});
