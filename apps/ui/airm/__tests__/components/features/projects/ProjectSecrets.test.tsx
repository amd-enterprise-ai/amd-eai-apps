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
  generateMockProjectSecrets,
  generateMockProjectSecretsWithParentSecret,
  generateMockSecrets,
} from '@/__mocks__/utils/secrets-mock';

import { ProjectStatus } from '@/types/enums/projects';
import { ProjectSecretStatus } from '@/types/enums/secrets';
import { ProjectWithMembers } from '@/types/projects';

import { ProjectSecrets } from '@/components/features/projects';

import wrapper from '@/__tests__/ProviderWrapper';
import { fetchProjectSecrets } from '@/services/app';
import { generateMockProjectStoragesWithParentStorage } from '@/__mocks__/utils/storages-mock';
import { DEFAULT_REFETCH_INTERVAL_FOR_PENDING_DATA } from '@amdenterpriseai/utils/app';
import { cloneDeep } from 'lodash';

vi.mock('@/services/app', async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>;
  return {
    ...actual,
    fetchProjectSecrets: vi.fn(),
  };
});

describe('ProjectSecrets', () => {
  const secrets = generateMockSecrets(1);
  const baseProject = generateMockProjects(1)[0];
  const project: ProjectWithMembers = {
    ...baseProject,
    users: [],
    invitedUsers: [],
  };

  const mockProjectSecrets = generateMockProjectSecretsWithParentSecret(1);

  const setup = (
    props?: Partial<React.ComponentProps<typeof ProjectSecrets>>,
  ) => {
    const onOpenChange = vi.fn();
    act(() => {
      render(
        <ProjectSecrets
          secrets={secrets}
          project={project}
          projectSecrets={props?.projectSecrets ?? { data: [] }}
          projectStorages={props?.projectStorages ?? { data: [] }}
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
      screen.getByText('list.headers.updatedAt.title'),
    ).toBeInTheDocument();

    expect(
      screen.getByRole('button', { name: /list\.filter\.type/ }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText('list.filter.scope.label'),
    ).not.toBeInTheDocument();
    expect(fetchProjectSecrets).toHaveBeenCalled();

    expect(
      screen.getByText('actions.addProjectSecret.label'),
    ).toBeInTheDocument();
  });

  it('render with disabled button if project is not ready', () => {
    setup({ project: { ...project, status: ProjectStatus.PENDING } });
    expect(
      screen.getByRole('button', { name: 'actions.addProjectSecret.label' }),
    ).toBeDisabled();
  });

  it('render not add button not disabled if project is ready', () => {
    setup({ project: { ...project, status: ProjectStatus.READY } });
    expect(
      screen.getByRole('button', { name: 'actions.addProjectSecret.label' }),
    ).not.toBeDisabled();
  });

  it('render delete row action to be not disabled when in synced state', () => {
    const mockSecrets = generateMockSecrets(1);
    const mockProjectId = 'mock-project-id';
    const mockProject = {
      ...project,
      status: ProjectStatus.READY,
      id: mockProjectId,
    };
    const mockProjectSecrets = generateMockProjectSecretsWithParentSecret(
      1,
      mockProjectId,
    );

    mockProjectSecrets[0].status = ProjectSecretStatus.SYNCED;
    mockSecrets[0].projectSecrets = mockProjectSecrets;

    setup({
      project: mockProject,
      secrets: mockSecrets,
      projectSecrets: { data: mockProjectSecrets },
    });
    const actionButton = screen.getByRole('button', {
      name: 'list.actions.label',
    });
    expect(actionButton).toBeInTheDocument();

    fireEvent.click(actionButton);

    const deleteAction = screen.getByText(
      'list.actions.delete.projectSecret.label',
    );
    expect(deleteAction).toBeInTheDocument();
    expect(deleteAction.parentNode).not.toHaveAttribute('data-disabled');
  });

  it('render delete row action to be not disabled when in deleting state', () => {
    const mockSecrets = generateMockSecrets(1);
    const mockProjectId = 'mock-project-id';
    const mockProject = {
      ...project,
      status: ProjectStatus.READY,
      id: mockProjectId,
    };
    const mockProjectSecrets = generateMockProjectSecretsWithParentSecret(
      1,
      mockProjectId,
    );

    mockProjectSecrets[0].status = ProjectSecretStatus.DELETING;
    mockSecrets[0].projectSecrets = mockProjectSecrets;

    setup({
      project: mockProject,
      secrets: mockSecrets,
      projectSecrets: { data: mockProjectSecrets },
    });
    const actionButton = screen.getByRole('button', {
      name: 'list.actions.label',
    });
    expect(actionButton).toBeInTheDocument();

    fireEvent.click(actionButton);

    const deleteAction = screen.getByText(
      'list.actions.delete.projectSecret.label',
    );
    expect(deleteAction).toBeInTheDocument();
    expect(deleteAction.parentNode).not.toHaveAttribute('data-disabled');
  });

  it('render delete row action to be not disabled when in pending state', () => {
    const mockSecrets = generateMockSecrets(1);
    const mockProjectId = 'mock-project-id';
    const mockProject = {
      ...project,
      status: ProjectStatus.READY,
      id: mockProjectId,
    };
    const mockProjectSecrets = generateMockProjectSecretsWithParentSecret(
      1,
      mockProjectId,
    );

    mockProjectSecrets[0].status = ProjectSecretStatus.PENDING;
    mockSecrets[0].projectSecrets = mockProjectSecrets;

    setup({
      project: mockProject,
      secrets: mockSecrets,
      projectSecrets: { data: mockProjectSecrets },
    });
    const actionButton = screen.getByRole('button', {
      name: 'list.actions.label',
    });
    expect(actionButton).toBeInTheDocument();

    fireEvent.click(actionButton);

    const deleteAction = screen.getByText(
      'list.actions.delete.projectSecret.label',
    );
    expect(deleteAction).toBeInTheDocument();
    expect(deleteAction.parentNode).not.toHaveAttribute(
      'data-disabled',
      'true',
    );
  });

  it('render delete row action to be disabled when secret is in projectStorages', () => {
    const mockSecrets = generateMockSecrets(1);
    const mockProjectId = 'mock-project-id';
    const mockProject = {
      ...project,
      status: ProjectStatus.READY,
      id: mockProjectId,
    };
    const mockProjectSecrets = generateMockProjectSecretsWithParentSecret(
      1,
      mockProjectId,
    );

    mockProjectSecrets[0].status = ProjectSecretStatus.SYNCED;
    mockSecrets[0].projectSecrets = mockProjectSecrets;

    const mockProjectStorages = generateMockProjectStoragesWithParentStorage(
      1,
      mockProjectId,
    );
    mockProjectStorages[0].storage.secretId = mockProjectSecrets[0].secret.id;

    setup({
      project: mockProject,
      secrets: mockSecrets,
      projectSecrets: { data: mockProjectSecrets },
      projectStorages: { data: mockProjectStorages },
    });
    const actionButton = screen.getByRole('button', {
      name: 'list.actions.label',
    });
    expect(actionButton).toBeInTheDocument();

    fireEvent.click(actionButton);

    const deleteAction = screen.getByRole('menuitem', {
      name: 'list.actions.delete.projectSecret.label',
    });
    expect(deleteAction).toHaveAttribute('aria-disabled', 'true');
  });

  it('delete button shows secrets delete confirm modal ', () => {
    const mockSecrets = generateMockSecrets(1);
    const mockProjectId = 'mock-project-id';
    mockProjectSecrets[0].status = ProjectSecretStatus.SYNCED;
    mockSecrets[0].projectSecrets = mockProjectSecrets;
    const mockProject = {
      ...project,
      status: ProjectStatus.READY,
      id: mockProjectId,
    };

    setup({
      project: mockProject,
      secrets: mockSecrets,
      projectSecrets: { data: mockProjectSecrets },
    });
    const actionButton = screen.getByRole('button', {
      name: 'list.actions.label',
    });
    expect(actionButton).toBeInTheDocument();

    fireEvent.click(actionButton);

    const deleteAction = screen.getByText(
      'list.actions.delete.projectSecret.label',
    );
    expect(deleteAction).toBeInTheDocument();
    act(() => {
      fireEvent.click(deleteAction);
    });

    expect(
      screen.getByText('form.deleteProjectSecret.title'),
    ).toBeInTheDocument();
  });

  it('filter will return correct secrets', async () => {
    const mockSecrets = generateMockSecrets(2);
    const mockProjectId = 'mock-project-id';
    const mockProjectSecrets = generateMockProjectSecrets(1, mockProjectId);
    mockProjectSecrets[0].status = ProjectSecretStatus.PENDING;
    mockSecrets[0].projectSecrets = mockProjectSecrets;
    const mockProject = {
      ...project,
      status: ProjectStatus.READY,
      id: mockProjectId,
    };

    await setup({
      project: mockProject,
      secrets: mockSecrets,
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

    expect(fetchProjectSecrets).toBeCalledTimes(1);
    act(() => {
      fireEvent.click(
        screen.getByRole('button', {
          name: 'actions.refresh.title',
        }),
      );
    });

    expect(fetchProjectSecrets).toBeCalledTimes(2);
  });

  it('refetches the data if project secret is pending', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const mockSecrets = generateMockSecrets(1);
    const mockProjectId = 'mock-project-id';
    const mockProject = {
      ...project,
      status: ProjectStatus.READY,
      id: mockProjectId,
    };
    const mockProjectSecrets = generateMockProjectSecretsWithParentSecret(
      1,
      mockProjectId,
    );

    mockProjectSecrets[0].status = ProjectSecretStatus.PENDING;
    mockSecrets[0].projectSecrets = mockProjectSecrets;

    // Immediately after page load
    vi.mocked(fetchProjectSecrets).mockResolvedValueOnce({
      data: mockProjectSecrets,
    });

    let syncedProjectSecrets = cloneDeep(mockProjectSecrets);
    syncedProjectSecrets[0].status = ProjectSecretStatus.SYNCED;
    // After 10 seconds, synced
    vi.mocked(fetchProjectSecrets).mockResolvedValueOnce({
      data: syncedProjectSecrets,
    });

    setup({
      project: mockProject,
      secrets: mockSecrets,
      projectSecrets: { data: mockProjectSecrets },
    });

    // On page load
    expect(fetchProjectSecrets).toBeCalledTimes(1);

    // After 10 seconds, synced secret
    await act(() =>
      vi.advanceTimersByTimeAsync(DEFAULT_REFETCH_INTERVAL_FOR_PENDING_DATA),
    );
    expect(fetchProjectSecrets).toBeCalledTimes(2);

    // No more polling
    await act(() =>
      vi.advanceTimersByTimeAsync(DEFAULT_REFETCH_INTERVAL_FOR_PENDING_DATA),
    );
    expect(fetchProjectSecrets).toBeCalledTimes(2);

    vi.useRealTimers();
  });

  it('should open add secret modal', () => {
    setup();

    fireEvent.click(
      screen.getByRole('button', { name: 'actions.addProjectSecret.label' }),
    );

    fireEvent.click(
      screen.getByText('actions.addProjectSecret.options.add.label'),
    );
    expect(screen.getByText('form.add.title')).toBeInTheDocument();
  });

  it('should open assign secret modal', () => {
    setup();

    fireEvent.click(
      screen.getByRole('button', { name: 'actions.addProjectSecret.label' }),
    );

    fireEvent.click(
      screen.getByText('actions.addProjectSecret.options.assign.label'),
    );
    expect(screen.getByText('form.assignOrgSecret.title')).toBeInTheDocument();
  });

  it('should render empty secrets list', () => {
    setup();

    expect(screen.getByText('title')).toBeInTheDocument();
    expect(screen.getByText('list.empty.description')).toBeInTheDocument();
  });
});
