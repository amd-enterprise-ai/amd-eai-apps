// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useTranslation } from 'next-i18next';

import { ConfirmationModal } from '@amdenterpriseai/components';

import type { LoraAdapter } from '@/types/artifacts';

type Props = {
  isOpen: boolean;
  onClose: () => void;
  onConfirmAction: (name: string) => void;
  adapter: LoraAdapter | undefined;
  loading: boolean;
};

export function DeleteLoraModal({
  isOpen,
  onClose,
  onConfirmAction,
  adapter,
  loading,
}: Props) {
  const { t } = useTranslation('loras', {
    keyPrefix: 'actions.delete.confirmation',
  });

  if (!adapter) return null;

  return (
    <ConfirmationModal
      confirmationButtonColor="danger"
      description={t('description', { name: adapter.displayName })}
      title={t('title')}
      isOpen={isOpen}
      loading={loading}
      onConfirm={() => !loading && onConfirmAction(adapter.name)}
      onClose={onClose}
    />
  );
}
