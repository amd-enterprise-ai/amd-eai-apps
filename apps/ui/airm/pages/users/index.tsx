// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  AirmDocsPage,
  airmDocumentationMapping,
  RelevantDocs,
  Tab,
  Tabs,
} from '@amdenterpriseai/components';
import { useOverlayState } from '@amdenterpriseai/hooks';

import { GetServerSideProps } from 'next';
import { getServerSession } from 'next-auth';
import { useTranslation } from 'next-i18next';

import { getUsers, getInvitedUsers } from '@/services/server';
import { getPageTranslations } from '@/utils/i18n';

import { authOptions } from '@amdenterpriseai/utils/server';

import { InvitedUsersResponse } from '@/types/users';
import { UsersResponse } from '@/types/users';

import { ActiveUsersTab, InvitedUsersTab } from '@/components/features/users';
import InviteUserModal from '@/components/features/users/InviteUserModal';
import { useAccessControl } from '@/hooks/useAccessControl';
import {
  DOCS_RESOURCE_MANAGER_BASE,
  WithDocumentationLink,
} from '@amdenterpriseai/utils/app';

interface Props {
  users: UsersResponse;
  invitedUsers: InvitedUsersResponse;
}

const UsersPage: React.FC<Props> & WithDocumentationLink = ({
  users,
  invitedUsers,
}: Props) => {
  const { t } = useTranslation('users');
  const { isOpen, onOpen, onOpenChange } = useOverlayState();
  const { isInviteEnabled } = useAccessControl();
  return (
    <div className="inline-flex flex-col w-full h-full max-h-full">
      <Tabs
        aria-label="Users tabs"
        variant="secondary"
        classNames={{
          panel: !isInviteEnabled && 'py-0',
          tabList: isInviteEnabled ? 'mt-8' : 'hidden',
        }}
      >
        <Tab key="active" title={t('tabs.active')}>
          <ActiveUsersTab initialData={users} onInviteUserClick={onOpen} />
        </Tab>
        {isInviteEnabled && (
          <Tab key="invited" title={t('tabs.invited')}>
            <InvitedUsersTab
              initialData={invitedUsers}
              onInviteUserClick={onOpen}
            />
          </Tab>
        )}
      </Tabs>

      <InviteUserModal
        usersInitialData={users}
        invitedUsersInitialData={invitedUsers}
        isOpen={isOpen}
        onOpenChange={onOpenChange}
      />
      <RelevantDocs docs={airmDocumentationMapping[AirmDocsPage.USERS]} />
    </div>
  );
};

UsersPage.documentationLink = `${DOCS_RESOURCE_MANAGER_BASE}/users/overview.html`;

export default UsersPage;

export const getServerSideProps: GetServerSideProps<Props> = async (
  context,
) => {
  const session = await getServerSession(context.req, context.res, authOptions);

  try {
    const usersData = await getUsers(session?.accessToken as string);
    const invitedUsersResponse = await getInvitedUsers(
      session?.accessToken as string,
    );

    return {
      props: {
        ...(await getPageTranslations(context.locale ?? 'en', ['users'])),
        invitedUsers: invitedUsersResponse,
        users: usersData,
      },
    };
  } catch (error) {
    console.error('Error checking access management status:', error);

    // On error, redirect to dashboard
    return {
      redirect: {
        destination: '/',
        permanent: false,
      },
    };
  }
};
