// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import React, { act } from 'react';

import { generateMockProjects } from '@/__mocks__/utils/project-mock';
import { generateMockSecrets } from '@/__mocks__/utils/secrets-mock';

import { Project } from '@/types/projects';
import { Secret } from '@/types/secrets';

import AssignSecret from '@/components/features/secrets/AssignSecret';

import wrapper from '@/__tests__/ProviderWrapper';

const mockUpdateSecretAssignment = vi.fn();

vi.mock('@/services/app', () => ({
  updateSecretAssignment: (...args: any[]) =>
    mockUpdateSecretAssignment(...args),
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

describe('AssignSecret', () => {
  const projects: Project[] = [];
  const secret: Secret = generateMockSecrets(1)[0];
  const selectedProjectIds: string[] = [];
  const onClose = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing if secret is null', () => {
    let container: HTMLElement | null = null;
    act(() => {
      const renderResult = render(
        <AssignSecret
          isOpen={true}
          secret={null}
          projects={[]}
          selectedProjectIds={selectedProjectIds}
          onClose={onClose}
          disabledProjectIds={[]}
        />,
        { wrapper },
      );
      container = renderResult.container;
    });
    expect(container!.firstChild).toBeNull();
  });

  it('renders form fields and buttons', () => {
    act(() => {
      render(
        <AssignSecret
          isOpen
          secret={secret}
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

  it('calls updateSecretAssignment and shows success toast on submit', async () => {
    const mockProjects: Project[] = generateMockProjects(3);

    mockUpdateSecretAssignment.mockResolvedValueOnce({});
    act(() =>
      render(
        <AssignSecret
          isOpen
          secret={secret}
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
      expect(mockUpdateSecretAssignment).toHaveBeenCalledWith(secret.id, {
        projectIds: [],
      });
      expect(toastSuccessMock).toHaveBeenCalled();
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('calls updateSecretAssignment disabled project id', async () => {
    mockUpdateSecretAssignment.mockResolvedValueOnce({});

    const mockProjects: Project[] = generateMockProjects(1);

    await act(() =>
      render(
        <AssignSecret
          isOpen
          secret={secret}
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
      expect(mockUpdateSecretAssignment).toHaveBeenCalledWith(secret.id, {
        projectIds: [],
      });
      expect(toastSuccessMock).toHaveBeenCalled();
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('calls updateSecretAssignment and select multiple project to be passed in', async () => {
    mockUpdateSecretAssignment.mockResolvedValueOnce({});

    const mockProjects: Project[] = generateMockProjects(3);

    await act(() =>
      render(
        <AssignSecret
          isOpen
          secret={secret}
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
      expect(mockUpdateSecretAssignment).toHaveBeenCalledWith(secret.id, {
        projectIds: [mockProjects[0].id, mockProjects[2].id],
      });
      expect(toastSuccessMock).toHaveBeenCalled();
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('calls updateSecretAssignment and mix of preselected and disabled to be passed in', async () => {
    mockUpdateSecretAssignment.mockResolvedValueOnce({});

    const mockProjects: Project[] = generateMockProjects(3);

    await act(() =>
      render(
        <AssignSecret
          isOpen
          secret={secret}
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
      expect(mockUpdateSecretAssignment).toHaveBeenCalledWith(secret.id, {
        projectIds: [mockProjects[1].id],
      });
      expect(toastSuccessMock).toHaveBeenCalled();
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('calls updateSecretAssignment and select a project to be passed in', async () => {
    mockUpdateSecretAssignment.mockResolvedValueOnce({});

    const mockProjects: Project[] = generateMockProjects(1);

    await act(() =>
      render(
        <AssignSecret
          isOpen
          secret={secret}
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
      expect(mockUpdateSecretAssignment).toHaveBeenCalledWith(secret.id, {
        projectIds: [mockProjects[0].id],
      });
      expect(toastSuccessMock).toHaveBeenCalled();
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('shows error toast on mutation error', async () => {
    mockUpdateSecretAssignment.mockRejectedValueOnce(new Error('fail'));

    act(() => {
      render(
        <AssignSecret
          isOpen
          secret={secret}
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
        <AssignSecret
          isOpen
          secret={secret}
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
