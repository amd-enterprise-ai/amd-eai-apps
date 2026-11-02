// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import React, { act } from 'react';

import { generateMockProjects } from '@/__mocks__/utils/project-mock';
import { generateMockStorages } from '@/__mocks__/utils/storages-mock';

import { Project } from '@/types/projects';
import { Storage } from '@/types/storages';

import { AssignStorage } from '@/components/features/storages';

import wrapper from '@/__tests__/ProviderWrapper';
import { updateStorageAssignment } from '@/services/app';

const mockUpdateStorageAssignment = vi.fn();

vi.mock('@/services/app', () => ({
  updateStorageAssignment: (...args: any[]) =>
    mockUpdateStorageAssignment(...args),
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

describe('AssignStorage', () => {
  const projects: Project[] = [];
  const storage: Storage = generateMockStorages(1)[0];
  const selectedProjectIds: string[] = [];
  const onClose = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders form fields and buttons', () => {
    act(() => {
      render(
        <AssignStorage
          isOpen
          storage={storage}
          projects={[]}
          selectedProjectIds={selectedProjectIds}
          onClose={onClose}
          disabledProjectIds={[]}
        />,
        { wrapper },
      );
    });

    expect(screen.getByText('form.assign.title')).toBeInTheDocument();
    const projectLabelElements = screen.getAllByText(
      'form.assign.field.projectIds.label',
    );
    expect(projectLabelElements.length).toBeGreaterThan(0);
    expect(screen.getByText('form.assign.action.save')).toBeInTheDocument();
    expect(screen.getByText('form.assign.action.cancel')).toBeInTheDocument();
  });

  it('calls updateStorageAssignment and shows success toast on submit', async () => {
    const mockProjects: Project[] = generateMockProjects(3);

    mockUpdateStorageAssignment.mockResolvedValueOnce({});
    act(() =>
      render(
        <AssignStorage
          isOpen
          storage={storage}
          projects={mockProjects}
          selectedProjectIds={selectedProjectIds}
          onClose={onClose}
          disabledProjectIds={[]}
        />,
        { wrapper },
      ),
    );

    fireEvent.click(screen.getByText('form.assign.action.save'));
    await waitFor(() => {
      expect(mockUpdateStorageAssignment).toHaveBeenCalledWith(storage.id, {
        projectIds: [],
      });
      expect(toastSuccessMock).toHaveBeenCalled();
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('calls updateStorageAssignment disabled project id', async () => {
    mockUpdateStorageAssignment.mockResolvedValueOnce({});

    const mockProjects: Project[] = generateMockProjects(1);

    await act(() =>
      render(
        <AssignStorage
          isOpen
          storage={storage}
          projects={mockProjects}
          selectedProjectIds={[]}
          disabledProjectIds={[mockProjects[0].id]}
          onClose={onClose}
        />,
        { wrapper },
      ),
    );

    await act(async () => {
      fireEvent.click(
        screen.getByRole('button', {
          name: /form.assign.field.projectIds.label/,
        }),
      );
    });
    const option = await screen.findByRole('option', { name: 'project-1' });
    await fireEvent.click(option);

    await fireEvent.click(screen.getByText('form.assign.action.save'));

    await waitFor(() => {
      expect(mockUpdateStorageAssignment).toHaveBeenCalledWith(storage.id, {
        projectIds: [],
      });
      expect(toastSuccessMock).toHaveBeenCalled();
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('calls updateStorageAssignment and select multiple project to be passed in', async () => {
    mockUpdateStorageAssignment.mockResolvedValueOnce({});

    const mockProjects: Project[] = generateMockProjects(3);

    await act(() =>
      render(
        <AssignStorage
          isOpen
          storage={storage}
          projects={mockProjects}
          selectedProjectIds={[]}
          disabledProjectIds={[]}
          onClose={onClose}
        />,
        { wrapper },
      ),
    );

    await act(async () => {
      fireEvent.click(
        screen.getByRole('button', {
          name: /form.assign.field.projectIds.label/,
        }),
      );
    });
    await fireEvent.click(
      await screen.findByRole('option', { name: 'project-1' }),
    );
    await fireEvent.click(screen.getByRole('option', { name: 'project-3' }));

    await fireEvent.click(screen.getByText('form.assign.action.save'));

    await waitFor(() => {
      expect(mockUpdateStorageAssignment).toHaveBeenCalledWith(storage.id, {
        projectIds: [mockProjects[0].id, mockProjects[2].id],
      });
      expect(toastSuccessMock).toHaveBeenCalled();
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('calls updateStorageAssignment and mix of preselected and disabled to be passed in', async () => {
    mockUpdateStorageAssignment.mockResolvedValueOnce({});

    const mockProjects: Project[] = generateMockProjects(3);

    await act(() =>
      render(
        <AssignStorage
          isOpen
          storage={storage}
          projects={mockProjects}
          selectedProjectIds={[mockProjects[0].id, mockProjects[1].id]}
          disabledProjectIds={[mockProjects[1].id]}
          onClose={onClose}
        />,
        { wrapper },
      ),
    );

    await act(async () => {
      fireEvent.click(
        screen.getByRole('button', {
          name: /form.assign.field.projectIds.label/,
        }),
      );
    });
    await fireEvent.click(
      await screen.findByRole('option', { name: 'project-1' }),
    );
    await fireEvent.click(screen.getByRole('option', { name: 'project-2' }));

    await fireEvent.click(screen.getByText('form.assign.action.save'));

    await waitFor(() => {
      expect(mockUpdateStorageAssignment).toHaveBeenCalledWith(storage.id, {
        projectIds: [mockProjects[1].id],
      });
      expect(toastSuccessMock).toHaveBeenCalled();
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('calls updateStorageAssignment and select a project to be passed in', async () => {
    mockUpdateStorageAssignment.mockResolvedValueOnce({});

    const mockProjects: Project[] = generateMockProjects(1);

    await act(() =>
      render(
        <AssignStorage
          isOpen
          storage={storage}
          projects={mockProjects}
          selectedProjectIds={selectedProjectIds}
          disabledProjectIds={[]}
          onClose={onClose}
        />,
        { wrapper },
      ),
    );

    await act(async () => {
      fireEvent.click(
        screen.getByRole('button', {
          name: /form.assign.field.projectIds.label/,
        }),
      );
    });
    const option = await screen.findByRole('option', { name: 'project-1' });
    await fireEvent.click(option);

    await fireEvent.click(screen.getByText('form.assign.action.save'));

    await waitFor(() => {
      expect(mockUpdateStorageAssignment).toHaveBeenCalledWith(storage.id, {
        projectIds: [mockProjects[0].id],
      });
      expect(toastSuccessMock).toHaveBeenCalled();
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('shows error toast on mutation error', async () => {
    mockUpdateStorageAssignment.mockRejectedValueOnce(new Error('fail'));

    act(() => {
      render(
        <AssignStorage
          isOpen
          storage={storage}
          projects={projects}
          selectedProjectIds={selectedProjectIds}
          onClose={onClose}
          disabledProjectIds={[]}
        />,
        { wrapper },
      );
    });
    fireEvent.click(screen.getByText('form.assign.action.save'));
    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalledWith(
        'form.assign.notification.error',
        expect.any(Error),
      );
    });
  });

  it('calls onClose when cancel button is clicked', () => {
    act(() => {
      render(
        <AssignStorage
          isOpen
          storage={storage}
          projects={projects}
          selectedProjectIds={selectedProjectIds}
          onClose={onClose}
          disabledProjectIds={[]}
        />,
        { wrapper },
      );
    });
    fireEvent.click(screen.getByText('form.assign.action.cancel'));
    expect(onClose).toHaveBeenCalled();
  });
});
