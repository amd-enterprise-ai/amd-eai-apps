// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  ActionButton,
  Card,
  CardBody,
  CardHeader,
  ConfirmationModal,
  Tooltip,
} from '@amdenterpriseai/components';
import { IconAlertTriangle } from '@tabler/icons-react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useSession } from 'next-auth/react';
import React, { useCallback, useMemo } from 'react';

import { useTranslation } from 'next-i18next';
import router from 'next/router';

import { useOverlayState, useSystemToast } from '@amdenterpriseai/hooks';

import { deleteUser as deleteUserAPI } from '@/services/app';

import { APIRequestError } from '@amdenterpriseai/utils/app';

interface Props {
  id: string;
  email: string;
}
export const DeleteUser: React.FC<Props> = ({ id, email }) => {
  const { t } = useTranslation('users');
  const { data: session } = useSession();

  const { toast } = useSystemToast();
  const queryClient = useQueryClient();
  const { isOpen, onOpen, onOpenChange } = useOverlayState();
  const { mutate: deleteUser, isPending } = useMutation({
    mutationFn: deleteUserAPI,
    onSuccess: () => {
      onOpenChange();
      queryClient.invalidateQueries({ queryKey: ['users'] });
      toast.success(t('detail.delete.notification.success'));
      router.push('/users');
    },
    onError: (error) => {
      toast.error(
        t('detail.delete.notification.error'),
        error as APIRequestError,
      );
      console.error('Error deleting user:', error);
      onOpenChange();
    },
  });

  const handleDelete = useCallback(() => {
    // Delete user
    deleteUser(id);
  }, [deleteUser, id]);

  const isLoggedInUser = useMemo(() => {
    return session?.user.email === email;
  }, [session, email]);

  return (
    <>
      <Card>
        <CardHeader>
          <h2 className="font-bold text-danger">{t('detail.delete.title')}</h2>
        </CardHeader>
        <CardBody className="flex flex-col gap-4">
          <p className="text-sm">{t('detail.delete.message')}</p>
          <Tooltip
            placement="top-start"
            content={
              isLoggedInUser
                ? t('detail.delete.action.disabled.sameUser')
                : null
            }
          >
            <span className="w-fit">
              <ActionButton
                primary
                aria-label={t('detail.delete.action.label') || ''}
                color="danger"
                onPress={onOpen}
                isDisabled={isLoggedInUser}
                icon={<IconAlertTriangle size={16} />}
              >
                {t('detail.delete.action.label')}
              </ActionButton>
            </span>
          </Tooltip>
        </CardBody>
      </Card>
      <ConfirmationModal
        confirmationButtonColor="danger"
        description={t('detail.delete.confirmation.description')}
        title={t('detail.delete.confirmation.title')}
        isOpen={isOpen}
        loading={isPending}
        onConfirm={handleDelete}
        onClose={onOpenChange}
      />
    </>
  );
};

export default DeleteUser;
