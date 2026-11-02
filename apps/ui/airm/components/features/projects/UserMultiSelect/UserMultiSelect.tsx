// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  Checkbox,
  Divider,
  SearchInput,
  UserListEntry,
} from '@amdenterpriseai/components';
import { IconUser } from '@tabler/icons-react';
import { useTranslation } from 'next-i18next';
import { useCallback, useMemo, useState } from 'react';

import { InvitedUser } from '@/types/users';
import { User } from '@/types/users';
import { UserRole } from '@amdenterpriseai/types';

interface SelectableUser {
  id: string;
  email: string;
  firstName?: string;
  lastName?: string;
  displayName?: string;
  subtitle?: string;
}

interface UserMultiSelectProps {
  users: User[];
  invitedUsers: InvitedUser[];
  onSelectionChange: (selectedIds: string[]) => void;
  searchPlaceholder: string;
  selectedUsersLabel: string;
  removeUserLabel: string;
  noUsersFoundLabel: string;
}

const UserIcon = () => (
  <div className="border border-default text-muted rounded-full min-w-8 h-8 flex justify-center items-center">
    <IconUser stroke="1.5" size={16} />
  </div>
);

const ROLE_KEYS: Record<UserRole, string> = {
  [UserRole.PLATFORM_ADMIN]:
    'settings.membersAndInvitedUsers.members.actions.add.form.users.roles.platformAdmin',
  [UserRole.TEAM_MEMBER]:
    'settings.membersAndInvitedUsers.members.actions.add.form.users.roles.teamMember',
};

export const UserMultiSelect: React.FC<UserMultiSelectProps> = ({
  users,
  invitedUsers,
  onSelectionChange,
  searchPlaceholder,
  selectedUsersLabel,
  removeUserLabel,
  noUsersFoundLabel,
}) => {
  const { t } = useTranslation('projects');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  const getRoleLabel = useCallback((role: UserRole) => t(ROLE_KEYS[role]), [t]);

  const allUsers: SelectableUser[] = useMemo(() => {
    const mappedUsers: SelectableUser[] = users.map((u) => ({
      id: u.id,
      email: u.email,
      firstName: u.firstName,
      lastName: u.lastName,
      subtitle: getRoleLabel(u.role),
    }));
    const mappedInvitedUsers: SelectableUser[] = invitedUsers.map((u) => ({
      id: u.id,
      email: u.email,
      subtitle: getRoleLabel(u.role),
    }));
    return [...mappedUsers, ...mappedInvitedUsers];
  }, [users, invitedUsers, getRoleLabel]);

  const filteredUsers = useMemo(() => {
    if (!searchQuery.trim()) {
      return allUsers;
    }
    const query = searchQuery.toLowerCase();
    return allUsers.filter((user) => {
      const fullName =
        user.displayName || `${user.lastName || ''}, ${user.firstName || ''}`;
      return (
        fullName.toLowerCase().includes(query) ||
        user.email.toLowerCase().includes(query) ||
        (user.firstName?.toLowerCase().includes(query) ?? false) ||
        (user.lastName?.toLowerCase().includes(query) ?? false)
      );
    });
  }, [allUsers, searchQuery]);

  const selectedUsers = useMemo(() => {
    return allUsers.filter((user) => selectedIds.includes(user.id));
  }, [allUsers, selectedIds]);

  const handleToggleUser = useCallback(
    (userId: string, isSelected: boolean) => {
      const newSelectedIds = isSelected
        ? [...selectedIds, userId]
        : selectedIds.filter((id) => id !== userId);
      setSelectedIds(newSelectedIds);
      onSelectionChange(newSelectedIds);
    },
    [selectedIds, onSelectionChange],
  );

  const handleRemoveUser = useCallback(
    (userId: string) => {
      const newSelectedIds = selectedIds.filter((id) => id !== userId);
      setSelectedIds(newSelectedIds);
      onSelectionChange(newSelectedIds);
    },
    [selectedIds, onSelectionChange],
  );

  const getUserDisplayName = (user: SelectableUser) => {
    if (user.displayName) return user.displayName;
    if (user.lastName && user.firstName)
      return `${user.lastName}, ${user.firstName}`;
    if (user.firstName) return user.firstName;
    if (user.lastName) return user.lastName;
    return user.email;
  };

  const getUserSubtitle = (user: SelectableUser) => {
    return user.subtitle || user.email;
  };

  return (
    <div className="flex flex-col gap-2">
      {/* Search input */}
      <SearchInput
        placeholder={searchPlaceholder}
        onValueChange={setSearchQuery}
        size="full"
        delay={200}
      />

      {/* Available users list */}
      <div className="max-h-64 overflow-y-auto border border-default rounded-lg">
        {filteredUsers.length === 0 ? (
          <div className="p-4 text-center text-muted text-sm">
            {noUsersFoundLabel}
          </div>
        ) : (
          filteredUsers.map((user) => {
            const isSelected = selectedIds.includes(user.id);
            return (
              <div
                key={user.id}
                className="flex items-center gap-3 px-3 py-2 hover:bg-default cursor-pointer"
                onClick={() => handleToggleUser(user.id, !isSelected)}
              >
                <Checkbox
                  isSelected={isSelected}
                  onValueChange={(checked) =>
                    handleToggleUser(user.id, checked)
                  }
                  aria-label={getUserDisplayName(user)}
                />
                <UserIcon />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium truncate">
                    {getUserDisplayName(user)}
                  </div>
                  <div className="text-xs text-muted truncate">
                    {getUserSubtitle(user)}
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Selected users section */}
      {selectedUsers.length > 0 && (
        <>
          <Divider className="my-2" />
          <div className="text-xs font-semibold text-foreground uppercase tracking-wide">
            {selectedUsersLabel}
          </div>
          <div className="max-h-72 overflow-y-auto">
            {selectedUsers.map((user) => (
              <UserListEntry
                key={user.id}
                name={user.email}
                description={user.subtitle || getUserDisplayName(user)}
                userIcon={<UserIcon />}
                onPress={() => handleRemoveUser(user.id)}
                buttonLabel={removeUserLabel}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
};

export default UserMultiSelect;
