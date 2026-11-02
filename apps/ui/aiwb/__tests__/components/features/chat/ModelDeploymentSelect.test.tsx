// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { act, fireEvent, render, screen } from '@testing-library/react';
import { Mock, vi } from 'vitest';

import type { Workload } from '@/types/workloads';

import { mockWorkloads } from '@/__mocks__/services/app/workloads.data';
import ProviderWrapper from '@/__tests__/ProviderWrapper';
import { ModelDeploymentSelect } from '@/components/features/chat/ModelDeploymentSelect';

import '@testing-library/jest-dom';

describe('ModelDeploymentSelect', () => {
  const baseInference = mockWorkloads.find(
    (workload) => workload.type === 'INFERENCE',
  ) as Workload;

  const workloads: Workload[] = [
    {
      ...baseInference,
      id: 'inference-running',
      displayName: 'Inference Running',
      status: 'Running',
      type: 'INFERENCE',
    },
    {
      ...baseInference,
      id: 'inference-pending',
      displayName: 'Inference Pending',
      status: 'Pending',
      type: 'INFERENCE',
    },
    {
      ...baseInference,
      id: 'workspace-running',
      displayName: 'Workspace Running',
      status: 'Running',
      type: 'WORKSPACE',
    },
  ];

  it('shows only running inference workloads by default', async () => {
    await act(async () => {
      render(
        <ProviderWrapper>
          <ModelDeploymentSelect
            workloads={workloads}
            onModelDeploymentChange={vi.fn()}
            label="Select model"
          />
        </ProviderWrapper>,
      );
    });
    const select = screen.getByRole('button', { name: /Select model/ });
    await act(async () => {
      fireEvent.click(select);
    });
    expect(screen.getAllByText('Inference Running').length).toBeGreaterThan(0);
    expect(screen.queryByText('Inference Pending')).not.toBeInTheDocument();
    expect(screen.queryByText('Workspace Running')).not.toBeInTheDocument();
  });

  it('calls onModelDeploymentChange when an option is selected', async () => {
    const onModelDeploymentChange = vi.fn() as Mock;
    await act(async () => {
      render(
        <ProviderWrapper>
          <ModelDeploymentSelect
            workloads={workloads}
            onModelDeploymentChange={onModelDeploymentChange}
            label="Select model"
            showOnlyRunningWorkloads={false}
          />
        </ProviderWrapper>,
      );
    });
    const select = screen.getByRole('button', { name: /Select model/ });
    await act(async () => {
      fireEvent.click(select);
    });
    const option = screen.getByRole('option', { name: 'inference-pending' });
    await act(async () => {
      fireEvent.click(option);
    });
    expect(onModelDeploymentChange).toHaveBeenCalledWith('inference-pending');
  });

  it('shows placeholder when no model is selected', async () => {
    await act(async () => {
      render(
        <ProviderWrapper>
          <ModelDeploymentSelect
            workloads={workloads}
            onModelDeploymentChange={vi.fn()}
            label="Select model"
          />
        </ProviderWrapper>,
      );
    });
    expect(
      screen.getByRole('button', { name: /Select model/ }),
    ).toHaveTextContent('Select model');
  });

  it('renders workload description for selected workload', async () => {
    let container: HTMLElement;
    await act(async () => {
      ({ container } = render(
        <ProviderWrapper>
          <ModelDeploymentSelect
            workloads={workloads}
            onModelDeploymentChange={vi.fn()}
            label="Select model"
            selectedModelId="inference-running"
            workloadDescriptions={{ 'inference-running': '1.0.0 · Throughput' }}
          />
        </ProviderWrapper>,
      ));
    });
    const trigger = container!.querySelector('[data-slot="select-trigger"]');
    expect(trigger).toHaveTextContent('1.0.0 · Throughput');
  });
});
