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
import { serverSideTranslations } from 'next-i18next/serverSideTranslations';

import { getProjects } from '@/services/server';
import { getSecrets } from '@/services/server';
import { getStorages } from '@/services/server';

import { generateMockProjects } from '@/__mocks__/utils/project-mock';
import {
  generateMockProjectSecrets,
  generateMockSecrets,
} from '@/__mocks__/utils/secrets-mock';
import { generateMockStorages } from '@/__mocks__/utils/storages-mock';

import { ProjectStatus } from '@/types/enums/projects';
import { SecretStatus } from '@/types/enums/secrets';

import StoragesPage, { getServerSideProps } from '@/pages/storages';

import wrapper from '@/__tests__/ProviderWrapper';

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

const mockFetchStorages = vi.fn();
const mockFetchSecrets = vi.fn();
const mockFetchProjects = vi.fn();
vi.mock('@/services/app', () => ({
  fetchStorages: (...args: any[]) => mockFetchStorages(...args),
  fetchSecrets: (...args: any[]) => mockFetchSecrets(...args),
  fetchProjects: (...args: any[]) => mockFetchProjects(...args),
}));

const mockAssignStorage = vi.hoisted(() => vi.fn());
vi.mock('@/components/features/storages', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@/components/features/storages')>();
  return {
    ...actual,
    AssignStorage: mockAssignStorage,
  };
});

describe('storages page', async () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should not crash the page', async () => {
    let container: HTMLElement | undefined;
    act(() => {
      const renderResult = render(
        <StoragesPage secrets={[]} projects={[]} storages={[]} />,
        {
          wrapper,
        },
      );
      container = renderResult.container;
    });
    expect(container).toBeTruthy();
  });

  it('calls fetchStorages, fetchSecrets and fetchProjects', () => {
    act(() => {
      render(<StoragesPage secrets={[]} projects={[]} storages={[]} />, {
        wrapper,
      });
    });
    expect(mockFetchStorages).toHaveBeenCalled();
    expect(mockFetchSecrets).toHaveBeenCalled();
    expect(mockFetchProjects).toHaveBeenCalled();
  });

  it('renders the SearchInput with correct placeholder', () => {
    act(() => {
      render(<StoragesPage secrets={[]} projects={[]} storages={[]} />, {
        wrapper,
      });
    });
    expect(
      screen.getByPlaceholderText('list.filter.search.placeholder'),
    ).toBeInTheDocument();
  });

  it('renders the Add button', () => {
    act(() => {
      render(<StoragesPage secrets={[]} projects={[]} storages={[]} />, {
        wrapper,
      });
    });
    expect(screen.getByText('actions.add.label')).toBeInTheDocument();
  });

  it('clicking on the Add button brings up Add Secret form', () => {
    const mockSecrets = generateMockSecrets(1);
    const mockStorages = generateMockStorages(1);

    mockSecrets[0].projectSecrets = generateMockProjectSecrets(3);
    act(() => {
      render(
        <StoragesPage
          secrets={mockSecrets}
          projects={[]}
          storages={mockStorages}
        />,
        { wrapper },
      );
    });
    fireEvent.click(screen.getByText('actions.add.label'));
    fireEvent.click(screen.getByText('actions.add.options.S3.label'));

    expect(screen.getByText('form.add.title')).toBeInTheDocument();
  });

  it('renders the table headers correctly', () => {
    act(() => {
      render(<StoragesPage storages={[]} secrets={[]} projects={[]} />, {
        wrapper,
      });
    });
    expect(screen.getByText('list.headers.name.title')).toBeInTheDocument();
    expect(screen.getByText('list.headers.type.title')).toBeInTheDocument();
    expect(screen.getByText('list.headers.status.title')).toBeInTheDocument();
    expect(screen.getByText('list.headers.scope.title')).toBeInTheDocument();
    expect(
      screen.getByText('list.headers.assignedTo.title'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('list.headers.createdAt.title'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('list.headers.createdBy.title'),
    ).toBeInTheDocument();
  });

  it('delete button shows secrets delete confirm modal ', () => {
    const mockSecrets = generateMockSecrets(1);
    const mockProjects = generateMockProjects(1);
    mockProjects[0].status = ProjectStatus.READY;
    mockSecrets[0].status = SecretStatus.SYNCED;
    const mockStorages = generateMockStorages(1);

    act(() => {
      render(
        <StoragesPage
          storages={mockStorages}
          secrets={mockSecrets}
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

  it('assign button shows storage edit form', async () => {
    const mockSecrets = generateMockSecrets(1);
    const mockProjects = generateMockProjects(1);
    const mockStorages = generateMockStorages(1);

    mockProjects[0].status = ProjectStatus.READY;
    mockSecrets[0].status = SecretStatus.SYNCED;

    await act(() => {
      render(
        <StoragesPage
          secrets={mockSecrets}
          projects={mockProjects}
          storages={mockStorages}
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
      expect(mockAssignStorage.mock.lastCall?.[0]).toEqual(
        expect.objectContaining({
          isOpen: true,
        }),
      );
    });
  });

  it('refetches the data if the refetch button is clicked', async () => {
    const mockSecrets = generateMockSecrets(1);
    const mockProjects = generateMockProjects(1);
    const mockStorages = generateMockStorages(1);

    act(() => {
      render(
        <StoragesPage
          secrets={mockSecrets}
          projects={mockProjects}
          storages={mockStorages}
        />,
        {
          wrapper,
        },
      );
    });

    expect(mockFetchStorages).toBeCalledTimes(1);
    act(() => {
      fireEvent.click(
        screen.getByRole('button', {
          name: 'actions.refresh.title',
        }),
      );
    });

    expect(mockFetchStorages).toBeCalledTimes(2);
  });

  it('filter will return correct storages', async () => {
    const mockSecrets = generateMockSecrets(1);
    const mockProjects = generateMockProjects(1);
    const mockStorages = generateMockStorages(1);

    act(() => {
      render(
        <StoragesPage
          secrets={mockSecrets}
          projects={mockProjects}
          storages={mockStorages}
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

  it('disabled list to be paseed to AssignStorage correctly', async () => {
    const mockProjects = generateMockProjects(2);
    const mockSecrets = generateMockSecrets(1);
    mockProjects[0].status = ProjectStatus.READY;
    mockProjects[1].status = ProjectStatus.PENDING;
    const mockStorages = generateMockStorages(1);

    await act(() => {
      render(
        <StoragesPage
          secrets={mockSecrets}
          projects={mockProjects}
          storages={mockStorages}
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
      expect(mockAssignStorage.mock.lastCall?.[0]).toEqual(
        expect.objectContaining({
          disabledProjectIds: expect.arrayContaining(['2']),
        }),
      );
    });
  });

  describe('getServerSideProps', () => {
    const context = {
      req: {},
      res: {},
      locale: 'en',
    };

    beforeEach(() => {
      vi.clearAllMocks();
    });

    it('returns props with fetched data when session is valid', async () => {
      (getServerSession as any).mockResolvedValue({
        user: { email: 'test@test.com' },
        accessToken: 'token',
      });
      (getProjects as any).mockResolvedValue({ data: [{ id: 1 }] });
      (getSecrets as any).mockResolvedValue({ data: [{ id: 2 }] });
      (getStorages as any).mockResolvedValue({ data: [{ id: 3 }] });

      const result = await getServerSideProps(context);

      expect(serverSideTranslations).toHaveBeenCalledWith('en', [
        'common',
        'sharedComponents',
        'storages',
        'secrets',
      ]);
      expect(result).toEqual({
        props: {
          projects: [{ id: 1 }],
          secrets: [{ id: 2 }],
          storages: [{ id: 3 }],
        },
      });
    });

    it('returns empty arrays if services return undefined', async () => {
      (getServerSession as any).mockResolvedValue({
        user: { email: 'test@test.com' },
        accessToken: 'token',
      });
      (getProjects as any).mockResolvedValue(undefined);
      (getSecrets as any).mockResolvedValue(undefined);
      (getStorages as any).mockResolvedValue(undefined);

      const result = await getServerSideProps(context);

      expect(result).toEqual({
        props: {
          projects: [],
          secrets: [],
          storages: [],
        },
      });
    });
  });
});
