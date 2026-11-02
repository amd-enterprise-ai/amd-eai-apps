// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { IconTrash } from '@tabler/icons-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useMemo, useState } from 'react';

import { Trans, useTranslation } from 'next-i18next';
import { useSession } from 'next-auth/react';
import { useOverlayState, useSystemToast } from '@amdenterpriseai/hooks';
import { useAccessControl } from '@/hooks/useAccessControl';

import {
  addUsersToProject as addUsersToProjectAPI,
  deleteUserFromProject as deleteUserFromProjectAPI,
} from '@/services/app';
import { fetchInvitedUsers, fetchUsers } from '@/services/app';

import {
  getCandidateInvitedUsersForProject,
  getCandidateUsersForProject,
} from '@/utils/projects';
import { displayTimestamp } from '@amdenterpriseai/utils/app';

import { TableColumns } from '@amdenterpriseai/types';
import { ProjectUsersTableField } from '@/types/enums/project-users-table-fields';
import { InviteMemberFormData } from '@/types/projects';
import { InvitedUsersResponse, User, UsersResponse } from '@/types/users';
import {
  ActionButton,
  ActionsToolbar,
  ClientSideDataTable,
  ConfirmationModal,
  DrawerForm,
} from '@amdenterpriseai/components';

import { UserMultiSelect } from './UserMultiSelect';
import { ZodType, z } from 'zod';
import { SortDirection } from '@amdenterpriseai/types';
import { ProjectWithMembers } from '@/types/projects';
import { CustomComparatorConfig } from '@amdenterpriseai/types';
import { compareUsersByFullName } from '@amdenterpriseai/utils/app';
import { getFilteredData } from '@amdenterpriseai/utils/app';
import { ClientSideDataFilter, FilterValueMap } from '@amdenterpriseai/types';
import { FilterComponentType } from '@amdenterpriseai/types';
interface Props {
  project: ProjectWithMembers;
}

const translationSet = 'projects';

const columns: TableColumns<ProjectUsersTableField | null> = [
  {
    key: ProjectUsersTableField.NAME,
    sortable: true,
  },
  {
    key: ProjectUsersTableField.EMAIL,
    sortable: true,
  },
  { key: ProjectUsersTableField.ROLE, sortable: true },
  { key: ProjectUsersTableField.LAST_ACTIVE, sortable: true },
];

const customComparator: CustomComparatorConfig<User, ProjectUsersTableField> = {
  [ProjectUsersTableField.NAME]: compareUsersByFullName,
};

const filterableFields: (keyof User)[] = ['firstName', 'lastName', 'email']; // Logical OR search of all fields

export const Members: React.FC<Props> = ({ project }) => {
  const { t } = useTranslation(translationSet);
  const { toast } = useSystemToast();
  const { data: session, update } = useSession();
  const { isAdministrator } = useAccessControl();

  const {
    isOpen: isAddUserOpen,
    onOpen: onAddUserOpen,
    onOpenChange: onAddUserOpenChange,
  } = useOverlayState();

  const {
    isOpen: isRemoveConfirmOpen,
    onOpen: onRemoveConfirmOpen,
    onOpenChange: onRemoveConfirmOpenChange,
  } = useOverlayState();

  const [filter, setFilter] = useState<ClientSideDataFilter<User>[]>([]);

  const filteredUsersData = useMemo(() => {
    return getFilteredData(project.users, filter);
  }, [filter, project.users]);

  const queryClient = useQueryClient();
  const [userBeingRemoved, setUserBeingRemoved] = useState<User>();

  const {
    data: users,
    isFetching,
    isRefetching,
    refetch,
    dataUpdatedAt,
  } = useQuery<UsersResponse>({
    queryKey: ['users'],
    queryFn: fetchUsers,
    enabled: !!isAdministrator,
  });

  const { data: invitedUsers } = useQuery<InvitedUsersResponse>({
    queryKey: ['invited-users'],
    queryFn: fetchInvitedUsers,
    enabled: !!isAdministrator,
  });

  const candidateUsers = useMemo(() => {
    return getCandidateUsersForProject(project, users?.data);
  }, [project, users]);

  const candidateInvitedUsers = useMemo(() => {
    return getCandidateInvitedUsersForProject(project, invitedUsers?.data);
  }, [project, invitedUsers]);

  // State for selected users in the add user drawer
  const [selectedUserIds, setSelectedUserIds] = useState<string[]>([]);

  const customRenderers: Partial<
    Record<ProjectUsersTableField, (item: User) => React.ReactNode | string>
  > = {
    [ProjectUsersTableField.NAME]: (item) =>
      `${item.firstName} ${item.lastName}`,
    [ProjectUsersTableField.LAST_ACTIVE]: (item) => {
      if (item.lastActiveAt) {
        return displayTimestamp(new Date(item.lastActiveAt));
      }
      return '-';
    },
  };

  // Form schema is minimal since we use selectedUserIds state for submission
  const formSchema = useMemo(
    () =>
      z.object({
        users: z.string().or(z.array(z.string())).or(z.undefined()),
      }),
    [],
  ) as ZodType<InviteMemberFormData>;

  const {
    mutate: deleteUserFromProject,
    isPending: isDeletingUserFromProject,
  } = useMutation({
    mutationFn: deleteUserFromProjectAPI,
    onSuccess: (data, variables) => {
      onRemoveConfirmOpenChange();
      toast.success(
        t(
          'settings.membersAndInvitedUsers.members.actions.remove.notification.success',
        ),
      );
      queryClient.invalidateQueries({ queryKey: ['project'] });

      const currentUser = users?.data.find(
        (u) => u.email === session?.user?.email,
      );
      const currentUserId = currentUser?.id;

      if (currentUserId && variables.userId === currentUserId) {
        console.log(
          'Current user removed themselves from project, refreshing token...',
        );
        update();
      } else {
        console.log('Current user not being changed, skipping token refresh');
      }
    },
    onError: () => {
      toast.error(
        t(
          'settings.membersAndInvitedUsers.members.actions.remove.notification.error',
        ),
      );
    },
  });

  const { mutate: addUsersToProject, isPending: isAddingUsersToProject } =
    useMutation({
      mutationFn: addUsersToProjectAPI,
      onSuccess: (data, variables) => {
        onAddUserOpenChange();
        toast.success(
          t(
            'settings.membersAndInvitedUsers.members.actions.add.notification.success',
          ),
        );

        queryClient.invalidateQueries({ queryKey: ['project'] });

        const currentUser = users?.data.find(
          (u) => u.email === session?.user?.email,
        );
        const currentUserId = currentUser?.id;

        if (currentUserId && variables.userIds.includes(currentUserId)) {
          console.log(
            'Current user added themselves to project, refreshing token...',
          );
          update();
        } else {
          console.log('Current user not found, skipping token refresh');
        }
      },
      onError: () => {
        toast.error(
          t(
            'settings.membersAndInvitedUsers.members.actions.add.notification.error',
          ),
        );
      },
    });

  const handleRemoveUserFromProject = useCallback(() => {
    if (project.id && userBeingRemoved?.id) {
      deleteUserFromProject({
        userId: userBeingRemoved.id,
        projectId: project.id,
      });
    }
  }, [deleteUserFromProject, project.id, userBeingRemoved]);

  const actions = () => {
    return [
      {
        key: 'Remove user',
        label: t(
          'settings.membersAndInvitedUsers.members.actions.remove.label',
        ),
        color: 'danger',
        startContent: <IconTrash className="text-danger" />,
        onPress: (user: User) => {
          setUserBeingRemoved(user);
          onRemoveConfirmOpen();
        },
      },
    ];
  };

  const handleSearchFilter = useCallback(
    (filter: FilterValueMap) => {
      if (
        filter.search &&
        !(
          Array.isArray(filter.search) &&
          filter.search.length === 1 &&
          filter.search[0] === ''
        )
      ) {
        setFilter([
          {
            values: filter.search,
            compositeFields: filterableFields.map((field) => ({ field })),
          },
        ]);
      } else {
        setFilter([]);
      }
    },
    [setFilter],
  );

  const filterConfig = {
    search: {
      name: 'search',
      label: t('list.filter.search.placeholder'),
      placeholder: t('list.filter.search.placeholder'),
      type: FilterComponentType.TEXT,
    },
  };

  return (
    <div>
      <div className="flex flex-col">
        <h3>{t('settings.membersAndInvitedUsers.members.title')}</h3>
        <ActionsToolbar
          filterConfig={filterConfig}
          onFilterChange={handleSearchFilter}
          onRefresh={refetch}
          updatedTimestamp={dataUpdatedAt}
          endContent={
            isAdministrator ? (
              <ActionButton
                primary
                aria-label={t(
                  'settings.membersAndInvitedUsers.members.actions.add.title',
                )}
                isDisabled={
                  candidateUsers.length === 0 &&
                  candidateInvitedUsers.length === 0
                }
                onPress={onAddUserOpen}
              >
                {t('settings.membersAndInvitedUsers.members.actions.add.title')}
              </ActionButton>
            ) : undefined
          }
        />
        <div className="mt-4 pb-8">
          {project.users.length ? (
            <ClientSideDataTable
              data={filteredUsersData}
              columns={columns}
              rowActions={isAdministrator ? actions : undefined}
              defaultSortByField={ProjectUsersTableField.NAME}
              defaultSortDirection={SortDirection.ASC}
              customRenderers={customRenderers}
              customComparator={customComparator}
              translation={t}
              idKey="id"
              translationKeyPrefix="users"
              isFetching={isFetching || isRefetching}
              isLoading={isDeletingUserFromProject}
            />
          ) : (
            <h4>{t('settings.membersAndInvitedUsers.members.empty')}</h4>
          )}
        </div>
      </div>
      <DrawerForm<InviteMemberFormData>
        isOpen={isAddUserOpen}
        isActioning={isAddingUsersToProject}
        isDisabled={selectedUserIds.length === 0}
        validationSchema={formSchema}
        title={t(
          'settings.membersAndInvitedUsers.members.actions.add.modal.title',
        )}
        cancelText={t(
          'settings.membersAndInvitedUsers.members.actions.add.modal.cancel',
        )}
        confirmText={t(
          'settings.membersAndInvitedUsers.members.actions.add.modal.confirm',
        )}
        onFormSuccess={() => {
          addUsersToProject({
            projectId: project.id,
            userIds: selectedUserIds,
          });
        }}
        onCancel={onAddUserOpenChange}
        renderFields={() => {
          return (
            <div className="flex flex-col gap-4">
              <Trans parent="p">
                {t(
                  'settings.membersAndInvitedUsers.members.actions.add.modal.intro',
                  {
                    project: project.name,
                  },
                )}
              </Trans>
              <UserMultiSelect
                users={candidateUsers}
                invitedUsers={candidateInvitedUsers}
                onSelectionChange={setSelectedUserIds}
                searchPlaceholder={t(
                  'settings.membersAndInvitedUsers.members.actions.add.form.users.searchPlaceholder',
                )}
                selectedUsersLabel={t(
                  'settings.membersAndInvitedUsers.members.actions.add.form.users.selectedUsers',
                )}
                removeUserLabel={t(
                  'settings.membersAndInvitedUsers.members.actions.add.form.users.removeUser',
                )}
                noUsersFoundLabel={t(
                  'settings.membersAndInvitedUsers.members.actions.add.form.users.noUsersFound',
                )}
              />
            </div>
          );
        }}
      />
      <ConfirmationModal
        description={t(
          'settings.membersAndInvitedUsers.members.actions.remove.description',
          {
            firstName: userBeingRemoved?.firstName,
            lastName: userBeingRemoved?.lastName,
            project: project.name,
          },
        )}
        title={t(
          'settings.membersAndInvitedUsers.members.actions.remove.confirm',
        )}
        isOpen={isRemoveConfirmOpen}
        loading={isDeletingUserFromProject}
        onConfirm={handleRemoveUserFromProject}
        onClose={onRemoveConfirmOpenChange}
        confirmationButtonColor="danger"
      />
    </div>
  );
};

export default Members;
