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
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { UserMultiSelect } from '@/components/features/projects/UserMultiSelect';
import { User } from '@/types/users';
import { InvitedUser } from '@/types/users';
import { UserRole } from '@amdenterpriseai/types';

// Mock debounce to execute immediately for testing purposes
vi.mock('lodash', async () => {
  const actual = await vi.importActual('lodash');
  return {
    ...(actual as object),
    debounce: (fn: Function) => fn,
  };
});

vi.mock('next-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      if (key.includes('platformAdmin')) return 'Platform Administrator';
      if (key.includes('teamMember')) return 'Team Member';
      return key;
    },
  }),
}));

const mockUsers: User[] = [
  {
    id: '1',
    email: 'john.doe@example.com',
    firstName: 'John',
    lastName: 'Doe',
    role: UserRole.TEAM_MEMBER,
  },
  {
    id: '2',
    email: 'jane.smith@example.com',
    firstName: 'Jane',
    lastName: 'Smith',
    role: UserRole.TEAM_MEMBER,
  },
];

const mockInvitedUsers: InvitedUser[] = [
  {
    id: '3',
    email: 'bob.wilson@example.com',
    role: UserRole.PLATFORM_ADMIN,
    invitedAt: '2024-01-01T00:00:00Z',
    invitedBy: 'admin@example.com',
  },
];

describe('UserMultiSelect Component', () => {
  const defaultProps = {
    users: mockUsers,
    invitedUsers: mockInvitedUsers,
    onSelectionChange: vi.fn(),
    searchPlaceholder: 'Search users',
    selectedUsersLabel: 'Selected users',
    removeUserLabel: 'Remove',
    noUsersFoundLabel: 'No users found',
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Rendering', () => {
    it('renders search input with correct placeholder', () => {
      render(<UserMultiSelect {...defaultProps} />);
      const searchInput = screen.getByPlaceholderText('Search users');
      expect(searchInput).toBeInTheDocument();
    });

    it('renders custom search placeholder', () => {
      render(
        <UserMultiSelect
          {...defaultProps}
          searchPlaceholder="Find team members"
        />,
      );
      const searchInput = screen.getByPlaceholderText('Find team members');
      expect(searchInput).toBeInTheDocument();
    });

    it('renders all users in the list', () => {
      render(<UserMultiSelect {...defaultProps} />);

      expect(screen.getByText('Doe, John')).toBeInTheDocument();
      expect(screen.getByText('Smith, Jane')).toBeInTheDocument();
      expect(screen.getByText('bob.wilson@example.com')).toBeInTheDocument();
    });

    it('renders user subtitles', () => {
      render(<UserMultiSelect {...defaultProps} />);

      expect(screen.getAllByText('Team Member')).toHaveLength(2);
      expect(screen.getByText('Platform Administrator')).toBeInTheDocument();
    });

    it('does not render selected users section when no users selected', () => {
      render(<UserMultiSelect {...defaultProps} />);

      expect(screen.queryByText('Selected users')).not.toBeInTheDocument();
    });

    it('renders selected users section when users are selected', async () => {
      render(<UserMultiSelect {...defaultProps} />);

      const userRow1 = screen
        .getByText('Doe, John')
        .closest('div[class*="flex items-center"]');
      const userRow2 = screen
        .getByText('Smith, Jane')
        .closest('div[class*="flex items-center"]');

      await act(async () => {
        fireEvent.click(userRow1!);
        fireEvent.click(userRow2!);
      });

      expect(screen.getByText('Selected users')).toBeInTheDocument();
    });

    it('renders custom selected users label', async () => {
      render(
        <UserMultiSelect {...defaultProps} selectedUsersLabel="CHOSEN USERS" />,
      );

      const userRow = screen
        .getByText('Doe, John')
        .closest('div[class*="flex items-center"]');
      await act(async () => {
        fireEvent.click(userRow!);
      });

      expect(screen.getByText('CHOSEN USERS')).toBeInTheDocument();
    });

    it('shows "No users found" when user list is empty', () => {
      render(
        <UserMultiSelect {...defaultProps} users={[]} invitedUsers={[]} />,
      );

      expect(screen.getByText('No users found')).toBeInTheDocument();
    });

    it('shows custom no users found label', () => {
      render(
        <UserMultiSelect
          {...defaultProps}
          users={[]}
          invitedUsers={[]}
          noUsersFoundLabel="No matching users"
        />,
      );

      expect(screen.getByText('No matching users')).toBeInTheDocument();
    });
  });

  describe('Selection', () => {
    it('calls onSelectionChange when clicking on a user row', async () => {
      const onSelectionChange = vi.fn();
      render(
        <UserMultiSelect
          {...defaultProps}
          onSelectionChange={onSelectionChange}
        />,
      );

      const userRow = screen
        .getByText('Doe, John')
        .closest('div[class*="flex items-center"]');
      await act(async () => {
        fireEvent.click(userRow!);
      });

      expect(onSelectionChange).toHaveBeenCalledWith(['1']);
    });

    it('calls onSelectionChange with added user when selecting', async () => {
      const onSelectionChange = vi.fn();
      render(
        <UserMultiSelect
          {...defaultProps}
          onSelectionChange={onSelectionChange}
        />,
      );

      const userRow1 = screen
        .getByText('Doe, John')
        .closest('div[class*="flex items-center"]');
      const userRow2 = screen
        .getByText('Smith, Jane')
        .closest('div[class*="flex items-center"]');
      await act(async () => {
        fireEvent.click(userRow1!);
      });
      await act(async () => {
        fireEvent.click(userRow2!);
      });

      expect(onSelectionChange).toHaveBeenLastCalledWith(['1', '2']);
    });

    it('calls onSelectionChange with removed user when deselecting via checkbox', async () => {
      const onSelectionChange = vi.fn();
      render(
        <UserMultiSelect
          {...defaultProps}
          onSelectionChange={onSelectionChange}
        />,
      );

      const userRow1 = screen
        .getByText('Doe, John')
        .closest('div[class*="flex items-center"]');
      const userRow2 = screen
        .getByText('Smith, Jane')
        .closest('div[class*="flex items-center"]');
      await act(async () => {
        fireEvent.click(userRow1!);
        fireEvent.click(userRow2!);
      });

      await act(async () => {
        fireEvent.click(userRow1!);
      });

      expect(onSelectionChange).toHaveBeenCalledWith(['2']);
    });

    it('shows checkboxes as selected for selected users', async () => {
      render(<UserMultiSelect {...defaultProps} />);

      const userRow = screen
        .getByText('Doe, John')
        .closest('div[class*="flex items-center"]');
      await act(async () => {
        fireEvent.click(userRow!);
      });

      expect(screen.getByText('Selected users')).toBeInTheDocument();
      expect(screen.getByText('john.doe@example.com')).toBeInTheDocument();
    });
  });

  describe('Selected Users Section', () => {
    it('displays selected users with email in the selected section', async () => {
      render(<UserMultiSelect {...defaultProps} />);

      const userRow1 = screen
        .getByText('Doe, John')
        .closest('div[class*="flex items-center"]');
      const userRow2 = screen
        .getByText('Smith, Jane')
        .closest('div[class*="flex items-center"]');
      await act(async () => {
        fireEvent.click(userRow1!);
      });
      await act(async () => {
        fireEvent.click(userRow2!);
      });

      expect(screen.getByText('Selected users')).toBeInTheDocument();
      expect(screen.getByText('Doe, John')).toBeInTheDocument();
      expect(screen.getByText('Smith, Jane')).toBeInTheDocument();
      expect(screen.getByText('john.doe@example.com')).toBeInTheDocument();
      expect(screen.getByText('jane.smith@example.com')).toBeInTheDocument();
    });

    it('calls onSelectionChange when removing user from selected section', async () => {
      const onSelectionChange = vi.fn();
      render(
        <UserMultiSelect
          {...defaultProps}
          onSelectionChange={onSelectionChange}
        />,
      );

      const userRow = screen
        .getByText('Doe, John')
        .closest('div[class*="flex items-center"]');
      await act(async () => {
        fireEvent.click(userRow!);
      });

      const removeButton = screen.getByRole('button', { name: 'Remove' });

      await act(async () => {
        fireEvent.click(removeButton);
      });

      expect(onSelectionChange).toHaveBeenCalledWith([]);
    });

    it('uses custom remove user label', async () => {
      render(<UserMultiSelect {...defaultProps} removeUserLabel="Delete" />);

      const userRow = screen
        .getByText('Doe, John')
        .closest('div[class*="flex items-center"]');
      await act(async () => {
        fireEvent.click(userRow!);
      });

      const removeButton = screen.getByRole('button', { name: 'Delete' });
      expect(removeButton).toBeInTheDocument();
    });
  });

  describe('Search Filtering', () => {
    it('filters users by first name', async () => {
      render(<UserMultiSelect {...defaultProps} />);

      const searchInput = screen.getByPlaceholderText('Search users');
      await act(async () => {
        fireEvent.change(searchInput, { target: { value: 'John' } });
      });

      expect(screen.getByText('Doe, John')).toBeInTheDocument();
      expect(screen.queryByText('Smith, Jane')).not.toBeInTheDocument();
      expect(
        screen.queryByText('bob.wilson@example.com'),
      ).not.toBeInTheDocument();
    });

    it('filters users by last name', async () => {
      render(<UserMultiSelect {...defaultProps} />);

      const searchInput = screen.getByPlaceholderText('Search users');
      await act(async () => {
        fireEvent.change(searchInput, { target: { value: 'Smith' } });
      });

      expect(screen.queryByText('Doe, John')).not.toBeInTheDocument();
      expect(screen.getByText('Smith, Jane')).toBeInTheDocument();
      expect(
        screen.queryByText('bob.wilson@example.com'),
      ).not.toBeInTheDocument();
    });

    it('filters users by email', async () => {
      render(<UserMultiSelect {...defaultProps} />);

      const searchInput = screen.getByPlaceholderText('Search users');
      await act(async () => {
        fireEvent.change(searchInput, { target: { value: 'bob.wilson' } });
      });

      expect(screen.queryByText('Doe, John')).not.toBeInTheDocument();
      expect(screen.queryByText('Smith, Jane')).not.toBeInTheDocument();
      expect(screen.getByText('bob.wilson@example.com')).toBeInTheDocument();
    });

    it('shows no users found when search has no matches', async () => {
      render(<UserMultiSelect {...defaultProps} />);

      const searchInput = screen.getByPlaceholderText('Search users');
      await act(async () => {
        fireEvent.change(searchInput, { target: { value: 'nonexistent' } });
      });

      expect(screen.getByText('No users found')).toBeInTheDocument();
    });

    it('search is case insensitive', async () => {
      render(<UserMultiSelect {...defaultProps} />);

      const searchInput = screen.getByPlaceholderText('Search users');
      await act(async () => {
        fireEvent.change(searchInput, { target: { value: 'JANE' } });
      });

      expect(screen.getByText('Smith, Jane')).toBeInTheDocument();
    });

    it('selected users section is not affected by search filter', async () => {
      render(<UserMultiSelect {...defaultProps} />);

      const userRow = screen
        .getByText('Doe, John')
        .closest('div[class*="flex items-center"]');
      await act(async () => {
        fireEvent.click(userRow!);
      });

      const searchInput = screen.getByPlaceholderText('Search users');
      await act(async () => {
        fireEvent.change(searchInput, { target: { value: 'Jane' } });
      });

      expect(screen.queryByText('Doe, John')).not.toBeInTheDocument();
      expect(screen.getByText('john.doe@example.com')).toBeInTheDocument();
    });
  });

  describe('Display Name Formatting', () => {
    it('displays lastName, firstName format', () => {
      render(<UserMultiSelect {...defaultProps} />);

      expect(screen.getByText('Doe, John')).toBeInTheDocument();
    });

    it('selected users show email in selected section', async () => {
      render(<UserMultiSelect {...defaultProps} />);

      const userRow = screen
        .getByText('Doe, John')
        .closest('div[class*="flex items-center"]');
      await act(async () => {
        fireEvent.click(userRow!);
      });

      expect(screen.getByText('Doe, John')).toBeInTheDocument();
      expect(screen.getByText('john.doe@example.com')).toBeInTheDocument();
    });
  });
});
