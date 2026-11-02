// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ActiveUsersTab } from '@/components/features/users/ActiveUsersTab';
import { mockUsersResponse } from '@/__mocks__/services/app/users.data';
import wrapper from '@/__tests__/ProviderWrapper';
import '@testing-library/jest-dom';
import { useAccessControl } from '@/hooks/useAccessControl';
import router from 'next/router';

// Mock useAccessControl
vi.mock('@/hooks/useAccessControl', () => ({
  useAccessControl: vi.fn(),
}));

// Mock useQuery to return our mock data
vi.mock('@tanstack/react-query', async (importOriginal) => {
  const actual = (await importOriginal()) as any;
  return {
    ...actual,
    useQuery: vi.fn(() => ({
      data: mockUsersResponse,
      isFetching: false,
      isRefetching: false,
      refetch: vi.fn(),
      dataUpdatedAt: new Date(),
    })),
  };
});

const mockUseAccessControl = vi.mocked(useAccessControl);

describe('ActiveUsersTab', () => {
  const mockOnInviteUserClick = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(router.push).mockClear();
    // Default mock setup
    mockUseAccessControl.mockReturnValue({
      isRoleManagementEnabled: true,
      isInviteEnabled: true,
      isAdministrator: true,
      smtpEnabled: true,
      isTempPasswordRequired: false,
    });
  });

  it('should render users list', () => {
    render(
      <ActiveUsersTab
        initialData={mockUsersResponse}
        onInviteUserClick={mockOnInviteUserClick}
      />,
      { wrapper },
    );

    mockUsersResponse.data.forEach((user) => {
      expect(
        screen.getByText(`${user.firstName} ${user.lastName}`),
      ).toBeInTheDocument();
      expect(screen.getByText(user.email)).toBeInTheDocument();
    });
  });

  it('should call onInviteUserClick when invite button is clicked', async () => {
    render(
      <ActiveUsersTab
        initialData={mockUsersResponse}
        onInviteUserClick={mockOnInviteUserClick}
      />,
      { wrapper },
    );

    const inviteButton = screen.getByLabelText('actions.addUser.label');
    fireEvent.click(inviteButton);

    expect(mockOnInviteUserClick).toHaveBeenCalledTimes(1);
  });

  it('should handle row click and navigate to user details', async () => {
    render(
      <ActiveUsersTab
        initialData={mockUsersResponse}
        onInviteUserClick={mockOnInviteUserClick}
      />,
      { wrapper },
    );

    const row = screen.getByText('FirstName 2 LastName 2').closest('tr');
    expect(row).toBeInTheDocument();

    if (row) {
      fireEvent.click(row);
    }

    expect(router.push).toHaveBeenCalledWith('/users/2');
  });

  it('should handle filter changes internally', async () => {
    render(
      <ActiveUsersTab
        initialData={mockUsersResponse}
        onInviteUserClick={mockOnInviteUserClick}
      />,
      { wrapper },
    );

    const filterInput = screen.getByPlaceholderText('list.filter.placeholder');

    // The component should handle its own filter logic now
    fireEvent.change(filterInput, { target: { value: 'test' } });

    // Verify the input value is updated (internal state management)
    await waitFor(() => {
      expect(filterInput).toHaveValue('test');
    });
  });

  describe('Created column', () => {
    it('should display Created column header', () => {
      render(
        <ActiveUsersTab
          initialData={mockUsersResponse}
          onInviteUserClick={mockOnInviteUserClick}
        />,
        { wrapper },
      );

      expect(
        screen.getByText('list.headers.createdAt.title'),
      ).toBeInTheDocument();
    });

    it('should display formatted date and time for users with createdAt', () => {
      render(
        <ActiveUsersTab
          initialData={mockUsersResponse}
          onInviteUserClick={mockOnInviteUserClick}
        />,
        { wrapper },
      );

      // DateDisplay uses DateSince: relative time ("X mins ago", "Yesterday at …") or absolute date
      const dateOrRelativeElements = screen.getAllByText((content) => {
        const text = content.trim();
        if (/^\d{1,2}\/\d{1,2}\/\d{4}/.test(text)) return true;
        if (/yesterday at/i.test(text)) return true;
        if (/\d+\s*(min|hr|hour|minute|day)s?\s*ago/i.test(text)) return true;
        if (/just now/i.test(text)) return true;
        return false;
      });
      expect(dateOrRelativeElements.length).toBeGreaterThan(0);
    });

    it('should have correct column order: Name, Email, Created, Roles', () => {
      render(
        <ActiveUsersTab
          initialData={mockUsersResponse}
          onInviteUserClick={mockOnInviteUserClick}
        />,
        { wrapper },
      );

      const headers = screen.getAllByRole('columnheader');

      expect(headers[0]).toHaveTextContent('list.headers.name.title');
      expect(headers[1]).toHaveTextContent('list.headers.email.title');
      expect(headers[2]).toHaveTextContent('list.headers.createdAt.title');
      expect(headers[3]).toHaveTextContent('list.headers.roles.title');
    });
  });

  // Additional tests for navigation scenarios
  describe('Navigation scenarios with different access control states', () => {
    it('should navigate correctly regardless of invite enabled status', () => {
      // Test that navigation works the same whether invite is enabled or not
      const accessControlStates = [
        { isInviteEnabled: false },
        { isInviteEnabled: true },
      ];

      accessControlStates.forEach((state) => {
        mockUseAccessControl.mockReturnValue({
          isRoleManagementEnabled: true,
          isAdministrator: true,
          ...state,
          isTempPasswordRequired: false,
          smtpEnabled: false,
        });

        const { unmount } = render(
          <ActiveUsersTab
            initialData={mockUsersResponse}
            onInviteUserClick={mockOnInviteUserClick}
          />,
          { wrapper },
        );

        // Navigation should work regardless of access control state
        const userRow = screen
          .getByText('FirstName 1 LastName 1')
          .closest('tr');
        if (userRow) {
          fireEvent.click(userRow);
        }

        expect(router.push).toHaveBeenCalledWith('/users/1');

        unmount();
        vi.mocked(router.push).mockClear();
      });
    });

    it('should handle navigation for different user IDs correctly', () => {
      render(
        <ActiveUsersTab
          initialData={mockUsersResponse}
          onInviteUserClick={mockOnInviteUserClick}
        />,
        { wrapper },
      );

      // Test multiple users
      const userTests = [
        { name: 'FirstName 2 LastName 2', expectedId: '2' },
        { name: 'FirstName 3 LastName 3', expectedId: '3' },
        { name: 'FirstName 4 LastName 4', expectedId: '4' },
      ];

      userTests.forEach((test) => {
        const userRow = screen.getByText(test.name).closest('tr');
        expect(userRow).toBeInTheDocument();

        if (userRow) {
          fireEvent.click(userRow);
        }

        expect(router.push).toHaveBeenCalledWith(`/users/${test.expectedId}`);
      });
    });
  });
});
