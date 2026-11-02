// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { IconTrash } from '@tabler/icons-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useState } from 'react';

import { useTranslation } from 'next-i18next';

import { useAccessControl } from '@/hooks/useAccessControl';
import { useOverlayState, useSystemToast } from '@amdenterpriseai/hooks';

import { fetchOrganization } from '@/services/app';
import { deleteUserFromProject as deleteUserFromProjectAPI } from '@/services/app';

import { TableColumns } from '@amdenterpriseai/types';
import { ProjectUsersTableField } from '@/types/enums/project-users-table-fields';
import { ProjectWithMembers } from '@/types/projects';
import { InvitedUser } from '@/types/users';

import InviteUserModal from '@/components/features/users/InviteUserModal';
import {
  ActionButton,
  ClientSideDataTable,
  ConfirmationModal,
  Tooltip,
} from '@amdenterpriseai/components';

interface Props {
  project: ProjectWithMembers;
}

const translationSet = 'projects';

export const InvitedUsers: React.FC<Props> = ({ project }) => {
  const { t } = useTranslation(translationSet);
  const { toast } = useSystemToast();
  const { isAdministrator } = useAccessControl();

  const columns: TableColumns<ProjectUsersTableField | null> = [
    {
      key: ProjectUsersTableField.EMAIL,
      sortable: true,
    },
    { key: ProjectUsersTableField.ROLE, sortable: true },
  ];

  const actions = () => {
    return [
      {
        key: 'Remove user',
        label: t(
          'settings.membersAndInvitedUsers.invitedUsers.actions.remove.label',
        ),
        color: 'danger',
        startContent: <IconTrash className="text-danger" />,
        onPress: (user: InvitedUser) => {
          setUserBeingRemoved(user);
          onRemoveConfirmOpen();
        },
      },
    ];
  };

  const {
    isOpen: isInviteUserOpen,
    onOpen: onInviteUserOpen,
    onOpenChange: onInviteUserOpenChange,
  } = useOverlayState();

  const {
    isOpen: isRemoveConfirmOpen,
    onOpen: onRemoveConfirmOpen,
    onOpenChange: onRemoveConfirmOpenChange,
  } = useOverlayState();

  const queryClient = useQueryClient();
  const [userBeingRemoved, setUserBeingRemoved] = useState<InvitedUser>();

  // Fetch organization identity provider status
  const { data: organizationData, isLoading: isLoadingOrgData } = useQuery({
    queryKey: ['organization'],
    queryFn: fetchOrganization,
  });

  const {
    mutate: deleteUserFromProject,
    isPending: isDeletingUserFromProject,
  } = useMutation({
    mutationFn: deleteUserFromProjectAPI,
    onSuccess: () => {
      onRemoveConfirmOpenChange();
      toast.success(
        t(
          'settings.membersAndInvitedUsers.invitedUsers.actions.remove.notification.success',
        ),
      );
      queryClient.invalidateQueries({ queryKey: ['project'] });
    },
    onError: () => {
      toast.error(
        t(
          'settings.membersAndInvitedUsers.invitedUsers.actions.remove.notification.error',
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

  return (
    <div>
      <div className="flex justify-between gap-4">
        <h3>{t('settings.membersAndInvitedUsers.invitedUsers.title')}</h3>
        {isAdministrator && (
          <Tooltip
            content={t('settings.membersAndInvitedUsers.invitedUsers.disabled')}
            isDisabled={!organizationData?.idpLinked}
          >
            <span>
              <ActionButton
                secondary
                aria-label={
                  t(
                    'settings.membersAndInvitedUsers.invitedUsers.actions.add.title',
                  ) || ''
                }
                onPress={onInviteUserOpen}
                isDisabled={!!organizationData?.idpLinked || isLoadingOrgData}
              >
                {t(
                  'settings.membersAndInvitedUsers.invitedUsers.actions.add.title',
                )}
              </ActionButton>
            </span>
          </Tooltip>
        )}
      </div>
      <div className="mt-4 pb-8">
        {project.invitedUsers.length ? (
          <ClientSideDataTable
            data={project.invitedUsers}
            columns={columns}
            rowActions={isAdministrator ? actions : undefined}
            defaultSortByField={ProjectUsersTableField.EMAIL}
            translation={t}
            idKey="id"
            translationKeyPrefix="users"
            isLoading={isDeletingUserFromProject}
          />
        ) : (
          <h4>{t('settings.membersAndInvitedUsers.invitedUsers.empty')}</h4>
        )}
      </div>
      {isAdministrator && (
        <InviteUserModal
          isOpen={isInviteUserOpen}
          onOpenChange={onInviteUserOpenChange}
          selectedProjectIds={[project.id]}
        />
      )}
      <ConfirmationModal
        description={t(
          'settings.membersAndInvitedUsers.invitedUsers.actions.remove.description',
          {
            email: userBeingRemoved?.email,
            project: project.name,
          },
        )}
        title={t(
          'settings.membersAndInvitedUsers.invitedUsers.actions.remove.confirm',
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

export default InvitedUsers;
