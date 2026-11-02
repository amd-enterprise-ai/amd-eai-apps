// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { render, screen, fireEvent } from '@testing-library/react';
import UndeployWorkspaceModal from '@/components/features/catalog/UndeployWorkspaceModal';

vi.mock('next-i18next', () => ({
  useTranslation: (_ns?: string, opts?: { keyPrefix?: string }) => ({
    t: (key: string, options?: { name?: string }) => {
      if (key === 'description' && options?.name) {
        return `Are you sure you want to undeploy <strong>${options.name}</strong>? Data stored in the persistent workspace storage will be accessible when you deploy it again.`;
      }
      return key;
    },
  }),
  Trans: ({ children }: { children?: React.ReactNode }) => <p>{children}</p>,
}));

describe('UndeployWorkspaceModal', () => {
  let mockOnOpenChange: (isOpen: boolean) => void;
  let mockOnConfirmAction: (workloadId: string) => void;

  const defaultProps = {
    isOpen: true,
    onOpenChange: vi.fn(),
    onConfirmAction: vi.fn(),
    workspaceToUndeploy: {
      workloadId: 'workload-123',
      displayName: 'JupyterLab',
    },
  };

  beforeEach(() => {
    mockOnOpenChange = vi.fn();
    mockOnConfirmAction = vi.fn();
    vi.clearAllMocks();
  });

  it('does not render when workspaceToUndeploy is undefined', () => {
    const { container } = render(
      <UndeployWorkspaceModal
        isOpen={true}
        onOpenChange={mockOnOpenChange}
        onConfirmAction={mockOnConfirmAction}
        workspaceToUndeploy={undefined}
      />,
    );

    expect(container.firstChild).toBeNull();
  });

  it('does not render modal content when isOpen is false', () => {
    render(
      <UndeployWorkspaceModal
        {...defaultProps}
        isOpen={false}
        onOpenChange={mockOnOpenChange}
        onConfirmAction={mockOnConfirmAction}
      />,
    );

    expect(screen.queryByText('title')).not.toBeInTheDocument();
  });

  it('renders modal with title and workspace name in bold', () => {
    render(
      <UndeployWorkspaceModal
        {...defaultProps}
        onOpenChange={mockOnOpenChange}
        onConfirmAction={mockOnConfirmAction}
      />,
    );

    expect(screen.getByText('title')).toBeInTheDocument();
    expect(
      screen.getByText(/Are you sure you want to undeploy.*JupyterLab/),
    ).toBeInTheDocument();
  });

  it('calls onConfirmAction with workload id when confirmed', () => {
    render(
      <UndeployWorkspaceModal
        {...defaultProps}
        onOpenChange={mockOnOpenChange}
        onConfirmAction={mockOnConfirmAction}
      />,
    );

    const confirmButton = screen.getByText('actions.confirm.title');
    fireEvent.click(confirmButton);

    expect(mockOnConfirmAction).toHaveBeenCalledWith(
      defaultProps.workspaceToUndeploy.workloadId,
    );
    expect(mockOnConfirmAction).toHaveBeenCalledTimes(1);
  });

  it('does not call onConfirmAction when loading', () => {
    render(
      <UndeployWorkspaceModal
        {...defaultProps}
        loading
        onOpenChange={mockOnOpenChange}
        onConfirmAction={mockOnConfirmAction}
      />,
    );

    const confirmButton = screen.getByText('actions.confirm.title');
    fireEvent.click(confirmButton);

    expect(mockOnConfirmAction).not.toHaveBeenCalled();
  });

  it('calls onOpenChange when close button is clicked', () => {
    render(
      <UndeployWorkspaceModal
        {...defaultProps}
        onOpenChange={mockOnOpenChange}
        onConfirmAction={mockOnConfirmAction}
      />,
    );

    const closeButton = screen.getByText('actions.close.title');
    fireEvent.click(closeButton);

    expect(mockOnConfirmAction).not.toHaveBeenCalled();
    expect(mockOnOpenChange).toHaveBeenCalledWith(false);
  });
});
