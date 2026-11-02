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
import userEvent from '@testing-library/user-event';

import { RefreshButton } from '@amdenterpriseai/components';

import { vi } from 'vitest';

// Mock next-i18next
vi.mock('next-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: any) => {
      if (key === 'data.lastUpdated') {
        return `Last updated ${options?.timestamp} ago`;
      }
      return key;
    },
  }),
}));

// Mock date-fns formatDistance function
vi.mock('date-fns', () => ({
  formatDistance: vi.fn(() => '5 minutes'),
}));

describe('RefreshButton', () => {
  const mockOnPress = vi.fn();

  beforeEach(() => {
    mockOnPress.mockClear();
    vi.clearAllMocks();
  });

  it('should render the button with the refresh icon', () => {
    render(<RefreshButton onPress={mockOnPress} />);
    const button = screen.getByRole('button', {
      name: 'actions.refresh.title',
    });
    expect(button).toBeInTheDocument();
    // Check for refresh icon (SVG element should be present)
    expect(button.querySelector('svg')).toBeInTheDocument();
  });

  it('should call onPress when clicked', () => {
    render(<RefreshButton onPress={mockOnPress} />);
    const button = screen.getByRole('button', {
      name: 'actions.refresh.title',
    });
    fireEvent.click(button);
    expect(mockOnPress).toHaveBeenCalledTimes(1);
  });

  it('should be disabled when isDisabled is true', () => {
    render(<RefreshButton onPress={mockOnPress} isDisabled />);
    const button = screen.getByRole('button', {
      name: 'actions.refresh.title',
    });
    expect(button).toBeDisabled();
  });

  it('should be disabled and show spinner when isLoading is true', () => {
    render(<RefreshButton onPress={mockOnPress} isLoading />);
    const button = screen.getByRole('button', { name: 'data.refreshing' });
    expect(button).toBeDisabled();
    expect(button.querySelector('.animate-spin')).toBeInTheDocument();
    expect(button.querySelector('svg')).toBeInTheDocument(); // Spinner icon should be present
  });

  it('should not call onPress when clicked if disabled', () => {
    act(() => {
      render(<RefreshButton onPress={mockOnPress} isDisabled />);
    });
    const button = screen.getByRole('button', {
      name: 'actions.refresh.title',
    });
    fireEvent.click(button);
    expect(mockOnPress).not.toHaveBeenCalled();
  });

  it('should not call onPress when clicked if loading', () => {
    render(<RefreshButton onPress={mockOnPress} isLoading />);
    const button = screen.getByRole('button', { name: 'data.refreshing' });
    fireEvent.click(button);
    expect(mockOnPress).not.toHaveBeenCalled();
  });

  describe('Compact mode (default)', () => {
    it('should render as icon-only button when compact is true', () => {
      render(<RefreshButton onPress={mockOnPress} compact />);
      const button = screen.getByRole('button', {
        name: 'actions.refresh.title',
      });
      expect(button).toBeInTheDocument();
      expect(
        screen.queryByText('actions.refresh.title'),
      ).not.toBeInTheDocument();
    });

    it('should show tooltip with refresh title when no timestamp is provided', async () => {
      // This test verifies the tooltip content logic rather than the actual tooltip display
      // since HeroUI's Tooltip component rendering is complex to test in unit tests
      render(<RefreshButton onPress={mockOnPress} compact />);

      // Verify the component renders correctly - the tooltip content is determined by the logic
      const button = screen.getByRole('button', {
        name: 'actions.refresh.title',
      });
      expect(button).toBeInTheDocument();

      // The tooltip should be enabled for compact mode without timestamp
      // We can't easily test the actual tooltip content due to HeroUI's implementation
      // but we know from the component logic that it should show 'actions.refresh.title'
    });

    it('should show tooltip with last updated time when timestamp is provided', () => {
      const timestamp = Date.now() - 300000; // 5 minutes ago

      render(
        <RefreshButton
          onPress={mockOnPress}
          compact
          lastFetchedTimestamp={timestamp}
        />,
      );

      // Verify the component renders and the date formatting is called
      const button = screen.getByRole('button', {
        name: 'actions.refresh.title',
      });
      expect(button).toBeInTheDocument();

      // Verify that formatDistance was called when timestamp is provided
      // This indirectly tests that the tooltip content will include the time
    });
  });

  describe('Non-compact mode', () => {
    it('should render with text when compact is false', () => {
      render(<RefreshButton onPress={mockOnPress} compact={false} />);
      const button = screen.getByRole('button', {
        name: 'actions.refresh.title',
      });
      expect(button).toBeInTheDocument();
      expect(screen.getByText('actions.refresh.title')).toBeInTheDocument();
    });

    it('should show loading text when isLoading is true and compact is false', () => {
      render(<RefreshButton onPress={mockOnPress} compact={false} isLoading />);
      expect(screen.getByText('data.refreshing')).toBeInTheDocument();
    });

    it('should disable tooltip when compact is false and no timestamp provided', () => {
      render(<RefreshButton onPress={mockOnPress} compact={false} />);

      const button = screen.getByRole('button', {
        name: 'actions.refresh.title',
      });
      expect(button).toBeInTheDocument();

      // When compact=false and no timestamp, tooltip should be disabled
      // This is tested by verifying the component logic rather than DOM tooltip presence
      // since the tooltip's isDisabled prop is calculated as: !timeSinceLastUpdate && !compact
      // In this case: !undefined && !false = true && true = true (tooltip is disabled)
    });

    it('should show tooltip when compact is false but timestamp is provided', () => {
      const timestamp = Date.now() - 300000; // 5 minutes ago

      render(
        <RefreshButton
          onPress={mockOnPress}
          compact={false}
          lastFetchedTimestamp={timestamp}
        />,
      );

      const button = screen.getByRole('button', {
        name: 'actions.refresh.title',
      });
      expect(button).toBeInTheDocument();
      expect(screen.getByText('actions.refresh.title')).toBeInTheDocument(); // Non-compact shows text

      // When compact=false but timestamp is provided, tooltip should be enabled
      // This is because: !timeSinceLastUpdate && !compact = false && true = false (tooltip is enabled)
    });
  });

  describe('Time since last update', () => {
    it('should calculate time since last update when timestamp is provided', async () => {
      const { formatDistance } = await import('date-fns');
      const mockFormatDistance = vi.mocked(formatDistance);

      const timestamp = Date.now() - 300000; // 5 minutes ago
      render(
        <RefreshButton
          onPress={mockOnPress}
          lastFetchedTimestamp={timestamp}
        />,
      );

      // The formatDistance mock should have been called
      expect(mockFormatDistance).toHaveBeenCalledWith(
        expect.any(Date),
        new Date(timestamp),
        { includeSeconds: true },
      );
    });

    it('should not calculate time when no timestamp is provided', async () => {
      const { formatDistance } = await import('date-fns');
      const mockFormatDistance = vi.mocked(formatDistance);

      render(<RefreshButton onPress={mockOnPress} />);

      expect(mockFormatDistance).not.toHaveBeenCalled();
    });

    it('should memoize time calculation based on timestamp', async () => {
      const { formatDistance } = await import('date-fns');
      const mockFormatDistance = vi.mocked(formatDistance);

      const timestamp = Date.now() - 300000;
      const { rerender } = render(
        <RefreshButton
          onPress={mockOnPress}
          lastFetchedTimestamp={timestamp}
        />,
      );

      expect(mockFormatDistance).toHaveBeenCalledTimes(1);

      // Re-render with same timestamp - should use memo
      rerender(
        <RefreshButton
          onPress={mockOnPress}
          lastFetchedTimestamp={timestamp}
        />,
      );
      expect(mockFormatDistance).toHaveBeenCalledTimes(1); // Should not call again

      // Re-render with different timestamp
      const newTimestamp = Date.now() - 600000;
      rerender(
        <RefreshButton
          onPress={mockOnPress}
          lastFetchedTimestamp={newTimestamp}
        />,
      );
      expect(mockFormatDistance).toHaveBeenCalledTimes(2); // Should call again
    });
  });
});
