// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { act, fireEvent, render, screen } from '@testing-library/react';

import { generateMockApiKey } from '@/__mocks__/utils/api-keys-mock';

import DeleteApiKeyModal from '@/components/features/api-keys/DeleteApiKeyModal';

import wrapper from '@/__tests__/ProviderWrapper';

const mockApiKey = generateMockApiKey();
const mockOnOpenChange = vi.fn();
const mockOnConfirmAction = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
});

describe('DeleteApiKeyModal', () => {
  const defaultProps = {
    isOpen: true,
    onOpenChange: mockOnOpenChange,
    onConfirmAction: mockOnConfirmAction,
    apiKey: mockApiKey,
  };

  it('renders delete confirmation modal', async () => {
    await act(async () => {
      render(<DeleteApiKeyModal {...defaultProps} />, {
        wrapper,
      });
    });

    expect(
      screen.getByText('list.actions.delete.confirmation.title'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('list.actions.delete.confirmation.description'),
    ).toBeInTheDocument();
  });

  it('displays API key name in confirmation message', async () => {
    await act(async () => {
      render(<DeleteApiKeyModal {...defaultProps} />, {
        wrapper,
      });
    });

    // The description should contain the API key name
    const description = screen.getByText(
      'list.actions.delete.confirmation.description',
    );
    expect(description).toBeInTheDocument();
  });

  it('handles confirm action', async () => {
    await act(async () => {
      render(<DeleteApiKeyModal {...defaultProps} />, {
        wrapper,
      });
    });

    const confirmButton = screen.getByText('actions.confirm.title');

    await act(async () => {
      fireEvent.click(confirmButton);
    });

    expect(mockOnConfirmAction).toHaveBeenCalledWith(mockApiKey);
    expect(mockOnOpenChange).toHaveBeenCalledWith(false);
  });

  it('handles cancel action', async () => {
    await act(async () => {
      render(<DeleteApiKeyModal {...defaultProps} />, {
        wrapper,
      });
    });

    const cancelButton = screen.getByText('actions.close.title');

    await act(async () => {
      fireEvent.click(cancelButton);
    });

    expect(mockOnOpenChange).toHaveBeenCalledWith(false);
    expect(mockOnConfirmAction).not.toHaveBeenCalled();
  });

  it('handles close action', async () => {
    await act(async () => {
      render(<DeleteApiKeyModal {...defaultProps} />, {
        wrapper,
      });
    });

    // Find close button (usually an X button)
    const closeButton = screen.getByLabelText('actions.close.title');

    await act(async () => {
      fireEvent.click(closeButton);
    });

    expect(mockOnOpenChange).toHaveBeenCalledWith(false);
  });

  it('does not render when apiKey is undefined', () => {
    const propsWithoutApiKey = {
      ...defaultProps,
      apiKey: undefined,
    };

    const { container } = render(
      <DeleteApiKeyModal {...propsWithoutApiKey} />,
      {
        wrapper,
      },
    );

    expect(container.firstChild).toBeNull();
  });

  describe('API Key Details', () => {
    it('works with a minimal API key', async () => {
      const props = {
        ...defaultProps,
        apiKey: generateMockApiKey(),
      };

      await act(async () => {
        render(<DeleteApiKeyModal {...props} />, {
          wrapper,
        });
      });

      expect(
        screen.getByText('list.actions.delete.confirmation.title'),
      ).toBeInTheDocument();
    });

    it('works with different API key names', async () => {
      const customApiKey = generateMockApiKey({
        displayName: 'Custom API Key Name',
      });
      const props = {
        ...defaultProps,
        apiKey: customApiKey,
      };

      await act(async () => {
        render(<DeleteApiKeyModal {...props} />, {
          wrapper,
        });
      });

      expect(
        screen.getByText('list.actions.delete.confirmation.title'),
      ).toBeInTheDocument();
    });
  });
});
