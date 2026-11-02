// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useTranslation } from 'next-i18next';

import { ConfirmationModal } from '@amdenterpriseai/components';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onConfirmAction: (profileName: string) => void;
  profile: { name: string; displayName: string } | undefined;
  loading: boolean;
}

export function DeleteCustomProfileModal({
  isOpen,
  onClose,
  onConfirmAction,
  profile,
  loading,
}: Props) {
  const { t } = useTranslation('models', {
    keyPrefix: 'customModels.profiles.actions.delete.confirmation',
  });

  if (!profile) return null;

  const handleConfirm = () => {
    if (loading) return;
    onConfirmAction(profile.name);
  };

  return (
    <ConfirmationModal
      confirmationButtonColor="danger"
      description={t('description', { name: profile.displayName })}
      title={t('title')}
      isOpen={isOpen}
      loading={loading}
      onConfirm={handleConfirm}
      onClose={onClose}
    />
  );
}
