// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { generateClustersMock } from '@/__mocks__/utils/cluster-mock';
import { generateMockProjectWithMembers } from '@/__mocks__/utils/project-mock';
import ProjectBasicInfoForm from '@/components/features/projects/ProjectBasicInfoForm';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import wrapper from '@/__tests__/ProviderWrapper';
import { updateProject } from '@/services/app';
import { Mock } from 'vitest';

vi.mock('@/services/app', async (importOriginal) => {
  return {
    ...(await importOriginal()),
    updateProject: vi.fn(),
  };
});

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

describe('ProjectBasicInfoForm', () => {
  it('should render correctly', () => {
    const { container } = render(
      <ProjectBasicInfoForm
        project={generateMockProjectWithMembers(1, 1)}
        cluster={generateClustersMock(1)[0]}
      />,
      { wrapper },
    );
    expect(container).toBeInTheDocument();
  });

  it('should render form with correct initial values', () => {
    const mockProject = generateMockProjectWithMembers(1, 1);
    const mockCluster = generateClustersMock(1)[0];
    mockProject.clusterId = mockCluster.id;

    const { container } = render(
      <ProjectBasicInfoForm project={mockProject} cluster={mockCluster} />,
      { wrapper },
    );

    expect(screen.getByDisplayValue(mockProject.name)).toBeInTheDocument();
    expect(
      screen.getByDisplayValue(mockProject.description),
    ).toBeInTheDocument();
    expect(screen.getByTestId('cluster-select')).toHaveTextContent(
      mockCluster.name,
    );
  });

  it('edit description field calls update project API correctly', async () => {
    const mockProject = generateMockProjectWithMembers(1, 1);
    const mockCluster = generateClustersMock(1)[0];
    mockProject.clusterId = mockCluster.id;

    act(() => {
      render(
        <ProjectBasicInfoForm project={mockProject} cluster={mockCluster} />,
        { wrapper },
      );
    });

    const descriptionInput = screen.getByPlaceholderText(
      'settings.form.basicInfo.description.placeholder',
    );
    expect(descriptionInput).toBeInTheDocument();

    await fireEvent.change(descriptionInput, {
      target: { value: 'some test value' },
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
              description: 'some test value',
            })
            .asymmetricMatch(call[0]),
        ),
      ).toBe(true);
    });
  });

  it('validates description length', async () => {
    const mockProject = generateMockProjectWithMembers(1, 1);
    const mockCluster = generateClustersMock(1)[0];
    mockProject.clusterId = mockCluster.id;

    act(() => {
      render(
        <ProjectBasicInfoForm project={mockProject} cluster={mockCluster} />,
        { wrapper },
      );
    });

    await fireEvent.change(
      screen.getByLabelText('settings.form.basicInfo.description.label'),
      {
        target: { value: 'a ' },
      },
    );

    const actionButton = screen.getByText('settings.form.actions.confirm');
    await fireEvent.click(actionButton);

    expect(
      await screen.findByText(
        'settings.form.basicInfo.description.validation.length',
      ),
    ).toBeInTheDocument();
  });

  it('reset will reset form to initial value', async () => {
    const mockProject = generateMockProjectWithMembers(1, 1);
    const mockCluster = generateClustersMock(1)[0];
    mockProject.clusterId = mockCluster.id;

    act(() => {
      render(
        <ProjectBasicInfoForm project={mockProject} cluster={mockCluster} />,
        { wrapper },
      );
    });

    const descriptionInput = screen.getByPlaceholderText(
      'settings.form.basicInfo.description.placeholder',
    );
    expect(descriptionInput).toBeInTheDocument();

    await fireEvent.change(descriptionInput, {
      target: { value: 'some test value' },
    });

    expect(screen.getByDisplayValue('some test value')).toBeInTheDocument();

    const resetButton = screen.getByText('settings.form.actions.reset');
    expect(resetButton).toBeInTheDocument();

    await fireEvent.click(resetButton);

    await waitFor(() => {
      expect(
        screen.getByDisplayValue(mockProject.description),
      ).toBeInTheDocument();
    });
  });

  it('call successful toast when resolved successfully', async () => {
    const mockProject = generateMockProjectWithMembers(1, 1);
    const mockCluster = generateClustersMock(1)[0];
    mockProject.clusterId = mockCluster.id;
    (updateProject as Mock).mockResolvedValue(Promise.resolve());

    act(() => {
      render(
        <ProjectBasicInfoForm project={mockProject} cluster={mockCluster} />,
        { wrapper },
      );
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
      render(
        <ProjectBasicInfoForm project={mockProject} cluster={mockCluster} />,
        { wrapper },
      );
    });

    const confirmButton = screen.getByText('settings.form.actions.confirm');
    expect(confirmButton).toBeInTheDocument();
    await fireEvent.click(confirmButton);
    await waitFor(() => {
      expect(updateProject).toHaveBeenCalled();
      expect(toastErrorMock).toHaveBeenCalled();
    });
  });
});
