// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { fireEvent, render, screen } from '@testing-library/react';

import type { Workload } from '@/types/workloads';

import DeleteWorkloadModal from '@/components/features/workloads/DeleteWorkloadModal';

import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockWorkload: Workload = {
  id: 'wl-123',
  type: 'INFERENCE',
  name: 'test-workload',
  displayName: 'Test Workload',
  createdBy: 'user',
  updatedBy: null,
  namespace: 'test-namespace',
  description: null,
  endpoints: {},
  createdAt: '2023-01-01T00:00:00Z',
  updatedAt: '2023-01-01T00:00:00Z',
  status: 'Running',
};

describe('DeleteWorkloadModal', () => {
  let onOpenChangeMock: ReturnType<typeof vi.fn<(isOpen: boolean) => void>>;
  let onConfirmActionMock: ReturnType<typeof vi.fn<(id: string) => void>>;

  beforeEach(() => {
    onOpenChangeMock = vi.fn<(isOpen: boolean) => void>();
    onConfirmActionMock = vi.fn<(id: string) => void>();
  });

  it('should not render if workload is undefined', () => {
    render(
      <DeleteWorkloadModal
        isOpen={true}
        onOpenChange={onOpenChangeMock}
        onConfirmAction={onConfirmActionMock}
        workload={undefined}
      />,
    );
    expect(
      screen.queryByText('list.actions.delete.confirmation.title'),
    ).not.toBeInTheDocument();
  });

  it('should render the modal when open with a workload', () => {
    render(
      <DeleteWorkloadModal
        isOpen={true}
        onOpenChange={onOpenChangeMock}
        onConfirmAction={onConfirmActionMock}
        workload={mockWorkload}
      />,
    );

    expect(
      screen.getByText('list.actions.delete.confirmation.title'),
    ).toBeInTheDocument();
  });

  it('should call onConfirmAction with workload id when confirmed', () => {
    render(
      <DeleteWorkloadModal
        isOpen={true}
        onOpenChange={onOpenChangeMock}
        onConfirmAction={onConfirmActionMock}
        workload={mockWorkload}
      />,
    );

    fireEvent.click(screen.getByText('actions.confirm.title'));

    expect(onConfirmActionMock).toHaveBeenCalledWith('wl-123');
    expect(onOpenChangeMock).toHaveBeenCalledWith(false);
  });

  it('should call onOpenChange when close button is clicked', () => {
    render(
      <DeleteWorkloadModal
        isOpen={true}
        onOpenChange={onOpenChangeMock}
        onConfirmAction={onConfirmActionMock}
        workload={mockWorkload}
      />,
    );

    fireEvent.click(screen.getByText('actions.close.title'));

    expect(onConfirmActionMock).not.toHaveBeenCalled();
    expect(onOpenChangeMock).toHaveBeenCalledWith(false);
  });
});
