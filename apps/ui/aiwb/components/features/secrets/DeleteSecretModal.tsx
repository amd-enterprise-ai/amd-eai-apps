// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'next-i18next';
import { useSystemToast } from '@amdenterpriseai/hooks';
import { deleteProjectSecret } from '@/lib/app/secrets';
import { APIRequestError } from '@amdenterpriseai/utils/app';
import { ConfirmationModal } from '@amdenterpriseai/components';
import { SecretResponseData } from '@/types/secrets';

interface Props {
  isOpen: boolean;
  onOpenChange: (isOpen: boolean) => void;
  secret: SecretResponseData | null;
  projectId: string;
  queryKeyToInvalidate: string[];
}

export default function DeleteSecretModal({
  isOpen,
  onOpenChange,
  secret,
  projectId,
  queryKeyToInvalidate,
}: Props) {
  const { t } = useTranslation('secrets');
  const { toast } = useSystemToast();
  const queryClient = useQueryClient();

  const { mutate: deleteSecretAction, isPending } = useMutation({
    mutationFn: async () => {
      if (!secret) {
        throw new Error('Secret is null');
      }
      return deleteProjectSecret(projectId, secret.metadata.name);
    },
    onSuccess: () => {
      toast.success(t('form.deleteProjectSecret.notification.success'));
      queryClient.invalidateQueries({ queryKey: ['secrets'] });
      queryClient.invalidateQueries({
        queryKey: ['projectSecrets', projectId],
      });
      queryClient.invalidateQueries({ queryKey: queryKeyToInvalidate });
      onOpenChange(false);
    },
    onError: (error) => {
      toast.error(
        t('form.deleteProjectSecret.notification.error'),
        error as APIRequestError,
      );
    },
  });

  if (!secret) return null;

  return (
    <ConfirmationModal
      confirmationButtonColor="danger"
      description={t('form.deleteProjectSecret.description', {
        name: secret.displayName ?? secret.metadata.name,
      })}
      title={t('form.deleteProjectSecret.title')}
      isOpen={isOpen}
      loading={isPending}
      onConfirm={deleteSecretAction}
      onClose={() => onOpenChange(false)}
    />
  );
}
