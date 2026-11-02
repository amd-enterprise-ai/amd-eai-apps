// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { act, fireEvent, render, screen } from '@testing-library/react';

import { DataRefresher } from '@amdenterpriseai/components';

describe('DataRefresher', () => {
  it('renders refresh button with default props', () => {
    act(() => {
      render(<DataRefresher onRefresh={vi.fn()} />);
    });
    expect(
      screen.getByRole('button', { name: /refresh/i }),
    ).toBeInTheDocument();
    expect(screen.getByText('Refresh')).toBeInTheDocument();
  });

  it('calls onRefresh when button is clicked', () => {
    const onRefresh = vi.fn();
    act(() => {
      render(<DataRefresher onRefresh={onRefresh} />);
    });
    fireEvent.click(screen.getByRole('button', { name: /refresh/i }));
    expect(onRefresh).toHaveBeenCalled();
  });

  it('shows last updated timestamp when lastFetchedTimestamp is provided', () => {
    const date = new Date('2023-01-01T12:00:00Z');
    act(() => {
      render(<DataRefresher onRefresh={vi.fn()} lastFetchedTimestamp={date} />);
    });

    expect(screen.getByText(/^Last update:/)).toBeInTheDocument();
  });

  it('shows refreshing state when isRefreshing is true', () => {
    act(() => {
      render(<DataRefresher onRefresh={vi.fn()} isRefreshing />);
    });
    const refreshButton = screen.getByRole('button', { name: /refresh/i });
    expect(refreshButton).toBeDisabled();
    expect(refreshButton).toBeInTheDocument();
  });

  it('shows compact mode (icon only)', () => {
    act(() => {
      render(<DataRefresher onRefresh={vi.fn()} compact />);
    });
    expect(screen.getByRole('button')).toBeInTheDocument();
    // Should not have text content
    expect(screen.getByRole('button').textContent).toBe('');
  });

  it('applies reversed class when reversed is true', () => {
    const { container } = render(
      <DataRefresher onRefresh={vi.fn()} reversed />,
    );
    expect(container.firstChild).toHaveClass('flex-row-reverse');
  });
});
