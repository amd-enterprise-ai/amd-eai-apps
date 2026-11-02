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

import { getServerSession } from 'next-auth';

import { fetchSecrets } from '@/services/app';
import { getProjects } from '@/services/server';
import { getSecrets } from '@/services/server';
import { getStorages } from '@/services/server';

import { generateMockProjects } from '@/__mocks__/utils/project-mock';
import {
  generateMockProjectSecrets,
  generateMockSecrets,
} from '@/__mocks__/utils/secrets-mock';
import { generateMockStorages } from '@/__mocks__/utils/storages-mock';
import { DEFAULT_REFETCH_INTERVAL_FOR_PENDING_DATA } from '@amdenterpriseai/utils/app';

import { ProjectStatus } from '@/types/enums/projects';
import { SecretStatus } from '@/types/enums/secrets';

import SecretsPage, { getServerSideProps } from '@/pages/secrets';

import wrapper from '@/__tests__/ProviderWrapper';
import { cloneDeep } from 'lodash';

vi.mock('@/services/app', () => ({
  fetchSecrets: vi.fn(),
}));

vi.mock('next-auth', () => ({
  getServerSession: vi.fn(),
}));
vi.mock('next-i18next/serverSideTranslations', () => ({
  serverSideTranslations: vi.fn().mockResolvedValue({ _translations: true }),
}));
vi.mock('@/services/server', () => ({
  getProjects: vi.fn(),
  getSecrets: vi.fn(),
  getStorages: vi.fn(),
}));

const mockAssignSecret = vi.hoisted(() => vi.fn());
vi.mock('@/components/features/secrets', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@/components/features/secrets')>();
  return {
    ...actual,
    AssignSecret: mockAssignSecret,
  };
});

describe('secrets page', async () => {
  it('should not crash the page', async () => {
    let container: HTMLElement | undefined;
    await act(() => {
      const renderResult = render(
        <SecretsPage
          storages={{ data: [] }}
          secrets={{ data: [] }}
          projects={[]}
        />,
        {
          wrapper,
        },
      );
      container = renderResult.container;
    });
    expect(container).toBeTruthy();
  });

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the SearchInput with correct placeholder', () => {
    act(() => {
      render(
        <SecretsPage
          storages={{ data: [] }}
          secrets={{ data: [] }}
          projects={[]}
        />,
        {
          wrapper,
        },
      );
    });
    expect(
      screen.getByPlaceholderText('list.filter.search.placeholder'),
    ).toBeInTheDocument();
  });

  it('renders the Add button', () => {
    act(() => {
      render(
        <SecretsPage
          storages={{ data: [] }}
          secrets={{ data: [] }}
          projects={[]}
        />,
        {
          wrapper,
        },
      );
    });
    expect(screen.getByText('actions.add')).toBeInTheDocument();
  });

  it('clicking on the Add button brings up Add Secret form', () => {
    const mockSecrets = generateMockSecrets(1);
    mockSecrets[0].projectSecrets = generateMockProjectSecrets(3);
    act(() => {
      render(
        <SecretsPage
          storages={{ data: [] }}
          secrets={{ data: mockSecrets }}
          projects={[]}
        />,
        {
          wrapper,
        },
      );
    });
    fireEvent.click(screen.getByText('actions.add'));
    expect(screen.getByText('form.add.title')).toBeInTheDocument();
  });

  it('renders the table headers correctly', () => {
    act(() => {
      render(
        <SecretsPage
          storages={{ data: [] }}
          secrets={{ data: [] }}
          projects={[]}
        />,
        {
          wrapper,
        },
      );
    });
    expect(screen.getByText('list.headers.name.title')).toBeInTheDocument();
    expect(screen.getByText('list.headers.type.title')).toBeInTheDocument();
    expect(screen.getByText('list.headers.status.title')).toBeInTheDocument();
    expect(screen.getByText('list.headers.scope.title')).toBeInTheDocument();
    expect(
      screen.getByText('list.headers.assignedTo.title'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('list.headers.updatedAt.title'),
    ).toBeInTheDocument();
  });

  it('refetches the data if secret is pending', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const mockSecrets = generateMockSecrets(1);
    const mockProjects = generateMockProjects(1);
    mockSecrets[0].status = SecretStatus.PENDING;

    // Immediately after page load
    vi.mocked(fetchSecrets).mockResolvedValueOnce({
      data: mockSecrets,
    });

    let syncedSecrets = cloneDeep(mockSecrets);
    syncedSecrets[0].status = SecretStatus.SYNCED;
    // After 10 seconds, synced
    vi.mocked(fetchSecrets).mockResolvedValueOnce({
      data: syncedSecrets,
    });

    act(() => {
      render(
        <SecretsPage
          storages={{ data: [] }}
          secrets={{ data: mockSecrets }}
          projects={mockProjects}
        />,
        {
          wrapper,
        },
      );
    });

    // On page load
    expect(fetchSecrets).toBeCalledTimes(1);

    // After 10 seconds, synced secret
    await act(() =>
      vi.advanceTimersByTimeAsync(DEFAULT_REFETCH_INTERVAL_FOR_PENDING_DATA),
    );
    expect(fetchSecrets).toBeCalledTimes(2);

    // No more polling
    await act(() =>
      vi.advanceTimersByTimeAsync(DEFAULT_REFETCH_INTERVAL_FOR_PENDING_DATA),
    );
    expect(fetchSecrets).toBeCalledTimes(2);

    vi.useRealTimers();
  });

  it('refetches the data if the refetch button is clicked', async () => {
    const mockSecrets = generateMockSecrets(1);
    const mockProjects = generateMockProjects(1);
    act(() => {
      render(
        <SecretsPage
          storages={{ data: [] }}
          secrets={{ data: mockSecrets }}
          projects={mockProjects}
        />,
        {
          wrapper,
        },
      );
    });

    expect(fetchSecrets).toBeCalledTimes(1);
    act(() => {
      fireEvent.click(
        screen.getByRole('button', {
          name: 'actions.refresh.title',
        }),
      );
    });

    expect(fetchSecrets).toBeCalledTimes(2);
  });

  it('delete button shows secrets delete confirm modal ', () => {
    const mockSecrets = generateMockSecrets(1);
    const mockProjects = generateMockProjects(1);
    mockProjects[0].status = ProjectStatus.READY;
    mockSecrets[0].status = SecretStatus.SYNCED;
    act(() => {
      render(
        <SecretsPage
          storages={{ data: [] }}
          secrets={{ data: mockSecrets }}
          projects={mockProjects}
        />,
        {
          wrapper,
        },
      );
    });
    const actionButton = screen.getByRole('button', {
      name: 'list.actions.label',
    });
    expect(actionButton).toBeInTheDocument();

    act(() => {
      fireEvent.click(actionButton);
    });

    const deleteAction = screen.getByText('list.actions.delete.label');
    expect(deleteAction).toBeInTheDocument();

    act(() => {
      fireEvent.click(deleteAction);
    });

    expect(screen.getByText('form.delete.title')).toBeInTheDocument();
  });

  it('delete action is not disabled when secret is in pending state', () => {
    const mockSecrets = generateMockSecrets(1);
    const mockProjects = generateMockProjects(1);
    mockProjects[0].status = ProjectStatus.READY;
    mockSecrets[0].status = SecretStatus.PENDING;
    act(() => {
      render(
        <SecretsPage
          storages={{ data: [] }}
          secrets={{ data: mockSecrets }}
          projects={mockProjects}
        />,
        {
          wrapper,
        },
      );
    });
    const actionButton = screen.getByRole('button', {
      name: 'list.actions.label',
    });
    expect(actionButton).toBeInTheDocument();

    act(() => {
      fireEvent.click(actionButton);
    });

    const deleteAction = screen.getByText('list.actions.delete.label');
    expect(deleteAction).toBeInTheDocument();
    expect(deleteAction.parentNode).not.toHaveAttribute(
      'data-disabled',
      'true',
    );
  });

  it('delete action is not disabled when secret is in deleting state', () => {
    const mockSecrets = generateMockSecrets(1);
    const mockProjects = generateMockProjects(1);
    mockProjects[0].status = ProjectStatus.READY;
    mockSecrets[0].status = SecretStatus.DELETING;
    act(() => {
      render(
        <SecretsPage
          storages={{ data: [] }}
          secrets={{ data: mockSecrets }}
          projects={mockProjects}
        />,
        {
          wrapper,
        },
      );
    });
    const actionButton = screen.getByRole('button', {
      name: 'list.actions.label',
    });
    expect(actionButton).toBeInTheDocument();

    act(() => {
      fireEvent.click(actionButton);
    });

    const deleteAction = screen.getByText('list.actions.delete.label');
    expect(deleteAction).toBeInTheDocument();
    expect(deleteAction.parentNode).not.toHaveAttribute('data-disabled');
  });

  it('assign button shows secrets edit form', async () => {
    const mockSecrets = generateMockSecrets(1);
    const mockProjects = generateMockProjects(1);
    mockProjects[0].status = ProjectStatus.READY;
    mockSecrets[0].status = SecretStatus.SYNCED;

    await act(() => {
      render(
        <SecretsPage
          storages={{ data: [] }}
          secrets={{ data: mockSecrets }}
          projects={mockProjects}
        />,
        {
          wrapper,
        },
      );
    });
    const actionButton = screen.getByRole('button', {
      name: 'list.actions.label',
    });
    expect(actionButton).toBeInTheDocument();

    await act(() => {
      fireEvent.click(actionButton);
    });

    const assignAction = screen.getByText('list.actions.assign.label');
    expect(assignAction).toBeInTheDocument();
    await act(() => {
      fireEvent.click(assignAction);
    });

    await waitFor(() => {
      expect(mockAssignSecret.mock.lastCall?.[0]).toEqual(
        expect.objectContaining({
          isOpen: true,
        }),
      );
    });
  });

  it('filter will return correct secrets', async () => {
    const mockSecrets = generateMockSecrets(1);
    const mockProjects = generateMockProjects(1);

    act(() => {
      render(
        <SecretsPage
          storages={{ data: [] }}
          secrets={{ data: mockSecrets }}
          projects={mockProjects}
        />,
        {
          wrapper,
        },
      );
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

  it('disabled list to be paseed to AssignSecret correctly', () => {
    const mockProjects = generateMockProjects(2);
    const mockSecrets = generateMockSecrets(1);
    mockProjects[0].status = ProjectStatus.READY;
    mockProjects[1].status = ProjectStatus.PENDING;

    act(() => {
      render(
        <SecretsPage
          storages={{ data: [] }}
          secrets={{ data: mockSecrets }}
          projects={mockProjects}
        />,
        {
          wrapper,
        },
      );
    });

    expect(mockAssignSecret.mock.lastCall?.[0]).toEqual(
      expect.objectContaining({
        disabledProjectIds: expect.arrayContaining(['2']),
      }),
    );
  });

  describe('getServerSideProps', () => {
    const mockSession = {
      user: { email: 'test@example.com' },
      accessToken: 'mock-token',
    };

    const mockSecrets = { data: [{ id: 'secret1' }] };
    const mockProjects = { data: [{ id: 'project1' }] };
    const mockStorages = { data: generateMockStorages(1) };

    beforeEach(() => {
      vi.resetModules();
    });

    it('returns props with secrets and projects when session is valid', async () => {
      (getServerSession as any).mockResolvedValue({
        user: { email: 'test@test.com' },
        accessToken: 'token',
      });
      (getProjects as any).mockResolvedValue(mockProjects);
      (getSecrets as any).mockResolvedValue(mockSecrets);
      (getStorages as any).mockResolvedValue(mockStorages);

      const result = await getServerSideProps({
        req: {},
        res: {},
        locale: 'en',
      });
      expect(result).toEqual({
        props: {
          projects: mockProjects.data,
          secrets: mockSecrets,
          storages: mockStorages,
        },
      });
    });

    it('returns empty arrays if secrets/projects are undefined', async () => {
      (getServerSession as any).mockResolvedValue({
        user: { email: 'test@test.com' },
        accessToken: 'token',
      });
      (getProjects as any).mockResolvedValue({
        data: [],
      });
      (getSecrets as any).mockResolvedValue({
        data: [],
      });
      (getStorages as any).mockResolvedValue({
        data: [],
      });

      const result = await getServerSideProps({
        req: {},
        res: {},
        locale: 'en',
      });
      expect(result).toEqual({
        props: {
          projects: [],
          secrets: { data: [] },
          storages: { data: [] },
        },
      });
    });
  });
});
