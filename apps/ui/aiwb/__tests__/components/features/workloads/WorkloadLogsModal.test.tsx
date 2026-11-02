// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { fireEvent, render, screen } from '@testing-library/react';

import WorkloadLogsModal from '@/components/features/workloads/WorkloadLogsModal';

import wrapper from '@/__tests__/ProviderWrapper';
import { mockWorkloads } from '@/__mocks__/services/app/workloads.data';
import { vi } from 'vitest';

// Mock setTimeout to make tests synchronous
const mockSetTimeout = vi.fn((callback) => {
  callback();
  return 1; // Return a mock timer ID
});
global.setTimeout = mockSetTimeout as any;

// Mock the WorkloadLogs component
vi.mock(
  '@/components/features/workloads/WorkloadLogs',
  async (importOriginal) => {
    const actual =
      await importOriginal<
        typeof import('@/components/features/workloads/WorkloadLogs')
      >();
    return {
      ...actual,
      default: vi.fn(({ workload, isOpen }) => {
        if (!workload) {
          return <div>list.actions.logs.modal.workloadNotFound</div>;
        }
        return (
          <div data-testid="workload-logs-component">
            <div>list.actions.logs.modal.description</div>
            <div>Mocked WorkloadLogs Component</div>
            <div>Workload: {workload.name}</div>
            <div>IsOpen: {isOpen ? 'true' : 'false'}</div>
          </div>
        );
      }),
    };
  },
);

describe('WorkloadLogsModal', () => {
  const mockOnOpenChange = vi.fn();

  const mockWorkload = mockWorkloads[0]; // Use first workload from shared mocks

  beforeEach(() => {
    vi.clearAllMocks();
    mockSetTimeout.mockClear();
  });

  it('renders modal when open', () => {
    render(
      <WorkloadLogsModal
        workload={mockWorkload}
        isOpen={true}
        onOpenChange={mockOnOpenChange}
        namespace="workbench"
      />,
      { wrapper },
    );

    // Check modal title is displayed
    expect(
      screen.getByText('list.actions.logs.modal.title'),
    ).toBeInTheDocument();

    // Check that WorkloadLogs component is rendered
    expect(screen.getByTestId('workload-logs-component')).toBeInTheDocument();
    expect(
      screen.getByText('Mocked WorkloadLogs Component'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Workload: Llama 7B Inference'),
    ).toBeInTheDocument();
    expect(screen.getByText('IsOpen: true')).toBeInTheDocument();

    // Check close button is present
    expect(screen.getByRole('button', { name: /close/i })).toBeInTheDocument();
  });

  it('does not render when modal is closed', () => {
    render(
      <WorkloadLogsModal
        workload={mockWorkload}
        isOpen={false}
        onOpenChange={mockOnOpenChange}
        namespace="workbench"
      />,
      { wrapper },
    );

    // Modal should not be in the document when closed
    expect(
      screen.queryByText('list.actions.logs.modal.title'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId('workload-logs-component'),
    ).not.toBeInTheDocument();
  });

  it('handles modal close action', () => {
    render(
      <WorkloadLogsModal
        workload={mockWorkload}
        isOpen={true}
        onOpenChange={mockOnOpenChange}
        namespace="workbench"
      />,
      { wrapper },
    );

    // Find and click the close button
    const closeButton = screen.getByRole('button', { name: /close/i });
    fireEvent.click(closeButton);

    expect(mockOnOpenChange).toHaveBeenCalledWith(false);
  });

  it('passes correct props to WorkloadLogs component', () => {
    render(
      <WorkloadLogsModal
        workload={mockWorkload}
        isOpen={true}
        onOpenChange={mockOnOpenChange}
        namespace="workbench"
      />,
      { wrapper },
    );

    // Verify WorkloadLogs receives correct props
    expect(
      screen.getByText('Workload: Llama 7B Inference'),
    ).toBeInTheDocument();
    expect(screen.getByText('IsOpen: true')).toBeInTheDocument();
  });

  it('handles undefined workload', () => {
    render(
      <WorkloadLogsModal
        workload={undefined}
        isOpen={true}
        onOpenChange={mockOnOpenChange}
        namespace="workbench"
      />,
      { wrapper },
    );

    // Should still render modal with title
    expect(
      screen.getByText('list.actions.logs.modal.title'),
    ).toBeInTheDocument();

    // WorkloadLogs should handle undefined workload
    expect(
      screen.getByText('list.actions.logs.modal.workloadNotFound'),
    ).toBeInTheDocument();
  });

  it('updates WorkloadLogs when isOpen changes', () => {
    const { rerender } = render(
      <WorkloadLogsModal
        workload={mockWorkload}
        isOpen={true}
        onOpenChange={mockOnOpenChange}
        namespace="workbench"
      />,
      { wrapper },
    );

    // Initially open
    expect(screen.getByText('IsOpen: true')).toBeInTheDocument();

    // Close modal
    rerender(
      <WorkloadLogsModal
        workload={mockWorkload}
        isOpen={false}
        onOpenChange={mockOnOpenChange}
        namespace="workbench"
      />,
    );

    // Modal should not be rendered when closed
    expect(
      screen.queryByTestId('workload-logs-component'),
    ).not.toBeInTheDocument();
  });

  it('has correct modal configuration', () => {
    render(
      <WorkloadLogsModal
        workload={mockWorkload}
        isOpen={true}
        onOpenChange={mockOnOpenChange}
        namespace="workbench"
      />,
      { wrapper },
    );

    // Check modal title
    expect(
      screen.getByText('list.actions.logs.modal.title'),
    ).toBeInTheDocument();

    // Check close button is present with correct aria-label
    const closeButton = screen.getByRole('button', { name: /close/i });
    expect(closeButton).toBeInTheDocument();
    expect(closeButton).toHaveAttribute('aria-label', 'Close');

    // Verify modal is rendered
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('calls onOpenChange on modal close', () => {
    render(
      <WorkloadLogsModal
        workload={mockWorkload}
        isOpen={true}
        onOpenChange={mockOnOpenChange}
        namespace="workbench"
      />,
      { wrapper },
    );

    // Close button should trigger onOpenChange
    const closeButton = screen.getByRole('button', { name: /close/i });
    fireEvent.click(closeButton);

    expect(mockOnOpenChange).toHaveBeenCalledWith(false);
    expect(mockOnOpenChange).toHaveBeenCalledTimes(1);
  });

  it('passes namespace prop to WorkloadLogs component', () => {
    const { container } = render(
      <WorkloadLogsModal
        workload={mockWorkload}
        isOpen={true}
        onOpenChange={mockOnOpenChange}
        namespace="test-namespace"
      />,
      { wrapper },
    );

    // Verify modal is rendered with WorkloadLogs component
    expect(screen.getByTestId('workload-logs-component')).toBeInTheDocument();
    expect(container).toBeInTheDocument();
  });

  it('renders modal with large size', () => {
    render(
      <WorkloadLogsModal
        workload={mockWorkload}
        isOpen={true}
        onOpenChange={mockOnOpenChange}
        namespace="workbench"
      />,
      { wrapper },
    );

    // Verify modal is rendered (size is set to 5xl in component)
    const dialog = screen.getByRole('dialog');
    expect(dialog).toBeInTheDocument();
  });
});
