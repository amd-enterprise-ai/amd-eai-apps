// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { act, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { PageFrameSize } from '@amdenterpriseai/types';

import { ClientSidePagination } from '@amdenterpriseai/components';

const useTranslation = (
  key: string,
  tokens?: { [s: string]: unknown } | ArrayLike<unknown>,
): string => {
  const translations: Record<string, string> = {
    'list.pagination.showing': 'Showing {{from}} to {{to}} of {{total}} users',

    'list.pagination.pageSize.label': 'Show',
    'list.pagination.pageSize.entities': 'users',
  };

  if (tokens) {
    let translatedText = translations[key] || key;
    Object.entries(tokens).forEach(([tokenKey, tokenValue]) => {
      translatedText = translatedText.replace(
        `{{${tokenKey}}}`,
        String(tokenValue),
      );
    });
    return translatedText;
  }
  return translations[key] || key;
};

describe('ClientSidePagination', () => {
  const mockOnFrameSizeChange = vi.fn();
  const mockOnPageChange = vi.fn();

  beforeEach(() => {
    mockOnFrameSizeChange.mockClear();
    mockOnPageChange.mockClear();
  });

  it('should render pagination component correctly', async () => {
    await act(() => {
      render(
        <ClientSidePagination
          currentPage={1}
          frameSize={PageFrameSize.SMALL}
          totalItems={50}
          // @ts-expect-error
          translation={useTranslation}
          onFrameSizeChange={mockOnFrameSizeChange}
          onPageChange={mockOnPageChange}
        />,
      );
    });

    expect(screen.getByText('Show')).toBeInTheDocument();
    expect(screen.getByText('users')).toBeInTheDocument();
    expect(screen.getByText('Showing 1 to 10 of 50 users')).toBeInTheDocument();
  });

  it('should call onFrameSizeChange when frame size is changed', async () => {
    await act(() => {
      render(
        <ClientSidePagination
          currentPage={1}
          frameSize={PageFrameSize.SMALL}
          totalItems={50}
          // @ts-expect-error
          translation={useTranslation}
          onFrameSizeChange={mockOnFrameSizeChange}
          onPageChange={mockOnPageChange}
        />,
      );
    });

    const user = userEvent.setup();
    const selectTrigger = screen.getByRole('button', { name: /Show/ });

    await user.click(selectTrigger);

    const options = await screen.findAllByRole('option');
    await user.click(options[1]);

    expect(mockOnFrameSizeChange).toHaveBeenCalledWith(PageFrameSize.MEDIUM);
  });

  it('should call onPageChange when page is changed', async () => {
    await act(() => {
      render(
        <ClientSidePagination
          currentPage={1}
          frameSize={PageFrameSize.SMALL}
          totalItems={50}
          // @ts-expect-error
          translation={useTranslation}
          onFrameSizeChange={mockOnFrameSizeChange}
          onPageChange={mockOnPageChange}
        />,
      );
    });

    const paginationButton = screen.getAllByLabelText('pagination item 3');
    if (paginationButton?.[0]) {
      fireEvent.click(paginationButton[0]);
    }

    expect(mockOnPageChange).toHaveBeenCalledWith(3);
  });

  it('should display correct pagination info for different frame sizes', async () => {
    let _rerender:
      | ((ui: React.ReactNode) => void)
      | ((arg0: React.ReactNode) => void);
    await act(() => {
      const { rerender } = render(
        <ClientSidePagination
          currentPage={1}
          frameSize={PageFrameSize.SMALL}
          totalItems={50}
          // @ts-expect-error
          translation={useTranslation}
          onFrameSizeChange={mockOnFrameSizeChange}
          onPageChange={mockOnPageChange}
        />,
      );
      _rerender = rerender;
    });

    expect(screen.getByText('Showing 1 to 10 of 50 users')).toBeInTheDocument();
    await act(() => {
      _rerender(
        <ClientSidePagination
          currentPage={1}
          frameSize={PageFrameSize.MEDIUM}
          totalItems={50}
          // @ts-expect-error
          translation={useTranslation}
          onFrameSizeChange={mockOnFrameSizeChange}
          onPageChange={mockOnPageChange}
        />,
      );
    });

    expect(screen.getByText('Showing 1 to 25 of 50 users')).toBeInTheDocument();
    await act(() => {
      _rerender(
        <ClientSidePagination
          currentPage={1}
          frameSize={PageFrameSize.LARGE}
          totalItems={50}
          // @ts-expect-error
          translation={useTranslation}
          onFrameSizeChange={mockOnFrameSizeChange}
          onPageChange={mockOnPageChange}
        />,
      );
    });

    expect(screen.getByText('Showing 1 to 50 of 50 users')).toBeInTheDocument();
  });

  it('should display correct pagination info for no entries', async () => {
    await act(() => {
      render(
        <ClientSidePagination
          currentPage={1}
          frameSize={PageFrameSize.SMALL}
          totalItems={0}
          // @ts-expect-error
          translation={useTranslation}
          onFrameSizeChange={mockOnFrameSizeChange}
          onPageChange={mockOnPageChange}
        />,
      );
    });

    expect(screen.queryByText('Showing')).not.toBeInTheDocument();
  });
});
