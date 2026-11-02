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

import { createProject } from '@/services/app';

import { generateMockProjects } from '@/__mocks__/utils/project-mock';
import { APIRequestError } from '@amdenterpriseai/utils/app';

import { ClusterStatus } from '@/types/enums/cluster-status';
import { GpuPreemptionPolicy } from '@/types/enums/gpu-preemption-policy';
import {
  GPU_PREEMPTION_DISABLED,
  ProjectWithResourceAllocation,
} from '@/types/projects';

import CreateProjectModal from '@/components/features/projects/CreateProjectModal';

import wrapper from '@/__tests__/ProviderWrapper';
import userEvent from '@testing-library/user-event';
import { Mock, vi } from 'vitest';
import { generateClustersMock } from '@/__mocks__/utils/cluster-mock';

const toastSuccessMock = vi.fn();
const toastErrorMock = vi.fn();
vi.mock('@amdenterpriseai/hooks', () => ({
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
    createProject: vi.fn(),
  };
});

describe('CreateProjectModal', () => {
  const onOpenChange = vi.fn();
  const onProjectCreate = vi.fn();
  const createProjects = (n: number): ProjectWithResourceAllocation[] =>
    generateMockProjects(n);
  const projects = createProjects(1);

  beforeEach(() => {
    toastSuccessMock.mockClear();
    toastErrorMock.mockClear();
  });

  it('renders the modal form', () => {
    act(() => {
      render(
        <CreateProjectModal
          isOpen={true}
          onOpenChange={onOpenChange}
          projects={projects}
          clusters={generateClustersMock(1)}
          onProjectCreate={onProjectCreate}
        />,
        { wrapper },
      );
    });

    expect(screen.getByText('modal.create.title')).toBeInTheDocument();
  });

  it('validates name uniqueness', async () => {
    await act(() => {
      render(
        <CreateProjectModal
          isOpen={true}
          onOpenChange={onOpenChange}
          projects={projects}
          clusters={generateClustersMock(1)}
          onProjectCreate={onProjectCreate}
        />,
        { wrapper },
      );
    });

    await fireEvent.change(
      screen.getByLabelText('modal.create.form.name.label'),
      {
        target: { value: 'project-1' },
      },
    );
    const actionButton = screen.getByText('modal.create.actions.confirm');
    await fireEvent.click(actionButton);

    await waitFor(() => {
      expect(
        screen.queryByText('modal.create.form.name.validation.unique'),
      ).toBeInTheDocument();
    });
  });

  it('validates name length', async () => {
    await act(() => {
      render(
        <CreateProjectModal
          isOpen={true}
          onOpenChange={onOpenChange}
          projects={projects}
          clusters={generateClustersMock(1)}
          onProjectCreate={onProjectCreate}
        />,
        { wrapper },
      );
    });

    await fireEvent.change(
      screen.getByLabelText('modal.create.form.name.label'),
      {
        target: { value: 'a ' },
      },
    );

    const actionButton = screen.getByText('modal.create.actions.confirm');
    fireEvent.click(actionButton);

    expect(
      await screen.findByText('modal.create.form.name.validation.length'),
    ).toBeInTheDocument();
  });

  it('validates name format', async () => {
    await act(() => {
      render(
        <CreateProjectModal
          isOpen={true}
          onOpenChange={onOpenChange}
          projects={projects}
          clusters={generateClustersMock(1)}
          onProjectCreate={onProjectCreate}
        />,
        { wrapper },
      );
    });

    await fireEvent.change(
      screen.getByLabelText('modal.create.form.name.label'),
      {
        target: { value: 'Project-001' },
      },
    );

    const actionButton = screen.getByText('modal.create.actions.confirm');
    fireEvent.click(actionButton);

    expect(
      await screen.findByText('modal.create.form.name.validation.format'),
    ).toBeInTheDocument();
  });

  it('rejects a name whose repeated hyphens would collapse into another name', async () => {
    // The project name becomes a namespace, and the namespace's slug is the object-storage
    // boundary. Slugging folds runs of hyphens, so 'data--science' addresses the same prefix
    // as a project legitimately named 'data-science'. The API refuses such a name; the form
    // has to refuse it too, or the user only learns about it from a 422.
    await act(() => {
      render(
        <CreateProjectModal
          isOpen={true}
          onOpenChange={onOpenChange}
          projects={projects}
          clusters={generateClustersMock(1)}
          onProjectCreate={onProjectCreate}
        />,
        { wrapper },
      );
    });

    await fireEvent.change(
      screen.getByLabelText('modal.create.form.name.label'),
      {
        target: { value: 'data--science' },
      },
    );

    const actionButton = screen.getByText('modal.create.actions.confirm');
    fireEvent.click(actionButton);

    expect(
      await screen.findByText('modal.create.form.name.validation.format'),
    ).toBeInTheDocument();
  });

  it('validates name length invalid with more than 41', async () => {
    await act(() => {
      render(
        <CreateProjectModal
          isOpen={true}
          onOpenChange={onOpenChange}
          projects={projects}
          clusters={generateClustersMock(1)}
          onProjectCreate={onProjectCreate}
        />,
        { wrapper },
      );
    });

    const nameInput = screen.getByLabelText(
      'modal.create.form.name.label',
    ) as HTMLInputElement;

    await fireEvent.change(nameInput, {
      target: {
        value: '01234567890123456789012345678901234567890',
      },
    });
    const user = userEvent.setup();
    await user.type(nameInput, '89abcde');
    expect(nameInput.value.length).toBe(41);
  });

  it('validates name length valid with 41 chars', async () => {
    await act(() => {
      render(
        <CreateProjectModal
          isOpen={true}
          onOpenChange={onOpenChange}
          projects={projects}
          clusters={generateClustersMock(1)}
          onProjectCreate={onProjectCreate}
        />,
        { wrapper },
      );
    });

    await fireEvent.change(
      screen.getByLabelText('modal.create.form.name.label'),
      {
        target: {
          value: '01234567890123456789012345678901234567890',
        },
      },
    );

    const actionButton = screen.getByText('modal.create.actions.confirm');
    fireEvent.click(actionButton);

    expect(
      await screen.queryByText('modal.create.form.name.validation.length'),
    ).not.toBeInTheDocument();
  });

  it('validates description length', async () => {
    await act(() => {
      render(
        <CreateProjectModal
          isOpen={true}
          onOpenChange={onOpenChange}
          projects={projects}
          clusters={generateClustersMock(1)}
          onProjectCreate={onProjectCreate}
        />,
        { wrapper },
      );
    });

    await fireEvent.change(
      screen.getByLabelText('modal.create.form.description.label'),
      {
        target: { value: 'a ' },
      },
    );

    const actionButton = screen.getByText('modal.create.actions.confirm');
    await fireEvent.click(actionButton);

    expect(
      await screen.findByText(
        'modal.create.form.description.validation.length',
      ),
    ).toBeInTheDocument();
  });

  it('validates cluster is required and does not submit without selection', async () => {
    await act(() => {
      render(
        <CreateProjectModal
          isOpen={true}
          onOpenChange={onOpenChange}
          projects={projects}
          clusters={generateClustersMock(2)}
          onProjectCreate={onProjectCreate}
        />,
        { wrapper },
      );
    });

    await fireEvent.change(
      screen.getByLabelText('modal.create.form.name.label'),
      { target: { value: 'new-project' } },
    );
    await fireEvent.change(
      screen.getByLabelText('modal.create.form.description.label'),
      { target: { value: 'Valid description for the project.' } },
    );
    // Do not select a cluster

    const actionButton = screen.getByText('modal.create.actions.confirm');
    fireEvent.click(actionButton);

    // Form should not submit when cluster is not selected (validation blocks submit)
    await waitFor(() => {
      expect(createProject).not.toHaveBeenCalled();
    });
  });

  it('allows selection only of healthy clusters', async () => {
    const user = userEvent.setup();
    const clusters = generateClustersMock(3);
    clusters[1].status = ClusterStatus.UNHEALTHY;
    clusters[2].status = ClusterStatus.VERIFYING;

    await act(() => {
      render(
        <CreateProjectModal
          isOpen={true}
          onOpenChange={onOpenChange}
          projects={projects}
          clusters={clusters}
          onProjectCreate={onProjectCreate}
        />,
        { wrapper },
      );
    });

    await user.click(
      screen.getByRole('button', {
        name: /modal.create.form.cluster.label/,
      }),
    );

    const healthy = await screen.findByRole('option', {
      name: clusters[0].name,
    });
    const unhealthy = screen.getByRole('option', { name: clusters[1].name });
    expect(healthy).toBeInTheDocument();
    expect(healthy).not.toHaveAttribute('aria-disabled', 'true');
    expect(unhealthy).toBeInTheDocument();
    expect(unhealthy).toHaveAttribute('aria-disabled', 'true');
    expect(
      screen.queryByRole('option', { name: clusters[2].name }),
    ).not.toBeInTheDocument();
  });

  it('detects max projects in cluster', async () => {
    const user = userEvent.setup();
    const clusters = generateClustersMock(1);
    await act(async () => {
      render(
        <CreateProjectModal
          isOpen={true}
          onOpenChange={onOpenChange}
          projects={createProjects(999)}
          clusters={clusters}
          onProjectCreate={onProjectCreate}
        />,
        { wrapper },
      );
    });

    await fireEvent.change(
      screen.getByLabelText('modal.create.form.name.label'),
      {
        target: { value: 'new-project' },
      },
    );
    await fireEvent.change(
      screen.getByLabelText('modal.create.form.description.label'),
      {
        target: { value: 'Description ' },
      },
    );

    await user.click(
      screen.getByRole('button', {
        name: /modal.create.form.cluster.label/,
      }),
    );
    await user.click(
      await screen.findByRole('option', { name: clusters[0].name }),
    );

    const actionButton = screen.getByText('modal.create.actions.confirm');
    await fireEvent.click(actionButton);

    // Validation blocks submit when cluster has reached max projects
    await waitFor(() => {
      expect(createProject).not.toHaveBeenCalled();
    });
  });

  it('calls createProject on form success', async () => {
    const user = userEvent.setup();
    (createProject as Mock).mockResolvedValueOnce({ id: 'newProjectId' }); // Mock successful creation
    const clusters = generateClustersMock(1);

    await act(async () => {
      render(
        <CreateProjectModal
          isOpen={true}
          onOpenChange={onOpenChange}
          projects={projects}
          clusters={clusters}
          onProjectCreate={onProjectCreate}
        />,
        { wrapper },
      );
    });

    await fireEvent.change(
      screen.getByLabelText('modal.create.form.name.label'),
      {
        target: { value: 'new-project' },
      },
    );
    await fireEvent.change(
      screen.getByLabelText('modal.create.form.description.label'),
      {
        target: { value: 'Description ' },
      },
    );

    await user.click(
      screen.getByRole('button', {
        name: /modal.create.form.cluster.label/,
      }),
    );
    await user.click(
      await screen.findByRole('option', { name: clusters[0].name }),
    );

    const actionButton = screen.getByText('modal.create.actions.confirm');
    await fireEvent.click(actionButton);

    await waitFor(() => {
      expect(createProject).toHaveBeenCalled();
      expect((createProject as Mock).mock.calls[0][0]).toEqual({
        name: 'new-project',
        description: 'Description',
        clusterId: 'cluster-1',
        quota: {
          cpuMilliCores: 0,
          memoryBytes: 0,
          ephemeralStorageBytes: 0,
          gpuCount: 0,
        },
        gpuPreemption: GPU_PREEMPTION_DISABLED,
      });
      expect(toastSuccessMock).toBeCalledWith(
        'modal.create.notification.success',
      );
      expect(onProjectCreate).toHaveBeenCalledWith('newProjectId');
    });
  });

  it('calls createProject on form error', async () => {
    const user = userEvent.setup();
    const clusters = generateClustersMock(1);

    const mockError = new APIRequestError('test error', 400);
    (createProject as Mock).mockRejectedValueOnce(mockError);
    await act(async () => {
      render(
        <CreateProjectModal
          isOpen={true}
          onOpenChange={onOpenChange}
          projects={projects}
          clusters={clusters}
          onProjectCreate={onProjectCreate}
        />,
        { wrapper },
      );
    });

    await fireEvent.change(
      screen.getByLabelText('modal.create.form.name.label'),
      {
        target: { value: 'new-project' },
      },
    );
    await fireEvent.change(
      screen.getByLabelText('modal.create.form.description.label'),
      {
        target: { value: 'Description ' },
      },
    );
    await user.click(
      screen.getByRole('button', {
        name: /modal.create.form.cluster.label/,
      }),
    );
    await user.click(
      await screen.findByRole('option', { name: clusters[0].name }),
    );

    const actionButton = screen.getByText('modal.create.actions.confirm');
    await fireEvent.click(actionButton);

    await waitFor(() => {
      expect(createProject).toHaveBeenCalled();
      expect((createProject as Mock).mock.calls[0][0]).toEqual({
        name: 'new-project',
        description: 'Description',
        clusterId: 'cluster-1',
        quota: {
          cpuMilliCores: 0,
          ephemeralStorageBytes: 0,
          gpuCount: 0,
          memoryBytes: 0,
        },
        gpuPreemption: GPU_PREEMPTION_DISABLED,
      });
      expect(toastErrorMock).toBeCalledWith(
        'modal.create.notification.error',
        mockError,
      );
    });
  });

  it('sends enabled gpuPreemption payload when pre-emption toggle is on', async () => {
    (createProject as Mock).mockResolvedValueOnce({ id: 'newProjectId' });
    const clusters = generateClustersMock(1);
    const user = userEvent.setup();

    await act(async () => {
      render(
        <CreateProjectModal
          isOpen={true}
          onOpenChange={onOpenChange}
          projects={projects}
          clusters={clusters}
          onProjectCreate={onProjectCreate}
        />,
        { wrapper },
      );
    });

    await fireEvent.change(
      screen.getByLabelText('modal.create.form.name.label'),
      { target: { value: 'new-project' } },
    );
    await fireEvent.change(
      screen.getByLabelText('modal.create.form.description.label'),
      { target: { value: 'Description ' } },
    );
    await user.click(
      screen.getByRole('button', {
        name: /modal.create.form.cluster.label/,
      }),
    );
    await user.click(
      await screen.findByRole('option', { name: clusters[0].name }),
    );

    await user.click(
      screen.getByRole('switch', {
        name: 'modal.create.form.preemption.toggle',
      }),
    );

    await waitFor(() => {
      expect(
        screen.getByRole('button', {
          name: /modal.create.form.preemption.policy.label/,
        }),
      ).toBeInTheDocument();
    });

    const thresholdInput = screen.getByLabelText(
      'modal.create.form.preemption.threshold.label',
    );
    await user.clear(thresholdInput);
    await user.type(thresholdInput, '10');
    const graceInput = screen.getByLabelText(
      'modal.create.form.preemption.gracePeriod.label',
    );
    await user.clear(graceInput);
    await user.type(graceInput, '30');

    const actionButton = screen.getByText('modal.create.actions.confirm');
    await fireEvent.click(actionButton);

    await waitFor(() => {
      expect(createProject).toHaveBeenCalled();
      expect((createProject as Mock).mock.calls[0][0]).toEqual({
        name: 'new-project',
        description: 'Description',
        clusterId: 'cluster-1',
        quota: {
          cpuMilliCores: 0,
          memoryBytes: 0,
          ephemeralStorageBytes: 0,
          gpuCount: 0,
        },
        gpuPreemption: {
          enabled: true,
          threshold: 10,
          gracePeriod: 1800,
          policy: GpuPreemptionPolicy.OnPressure,
        },
      });
    });
  });

  it('does not submit when pre-emption is on and idle timer is below minimum', async () => {
    (createProject as Mock).mockClear();
    const clusters = generateClustersMock(1);
    const user = userEvent.setup();

    await act(async () => {
      render(
        <CreateProjectModal
          isOpen={true}
          onOpenChange={onOpenChange}
          projects={projects}
          clusters={clusters}
          onProjectCreate={onProjectCreate}
        />,
        { wrapper },
      );
    });

    await fireEvent.change(
      screen.getByLabelText('modal.create.form.name.label'),
      { target: { value: 'new-project' } },
    );
    await fireEvent.change(
      screen.getByLabelText('modal.create.form.description.label'),
      { target: { value: 'Valid description for the project.' } },
    );
    await user.click(
      screen.getByRole('button', {
        name: /modal.create.form.cluster.label/,
      }),
    );
    await user.click(
      await screen.findByRole('option', { name: clusters[0].name }),
    );

    await user.click(
      screen.getByRole('switch', {
        name: 'modal.create.form.preemption.toggle',
      }),
    );

    const graceInput = screen.getByLabelText(
      'modal.create.form.preemption.gracePeriod.label',
    );
    await user.clear(graceInput);
    await user.type(graceInput, '10');

    await user.click(screen.getByText('modal.create.actions.confirm'));

    await waitFor(() => {
      expect(
        screen.getByText('modal.create.form.preemption.validation.graceMin'),
      ).toBeInTheDocument();
    });
    expect(createProject).not.toHaveBeenCalled();
  });
});
