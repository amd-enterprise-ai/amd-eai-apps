// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useTranslation } from 'next-i18next';

import { ConfirmationModal } from '@amdenterpriseai/components';

export interface WorkspaceToUndeploy {
  workloadId: string;
  displayName: string;
}

interface UndeployWorkspaceModalProps {
  isOpen: boolean;
  onOpenChange: (isOpen: boolean) => void;
  onConfirmAction: (workloadId: string) => void;
  workspaceToUndeploy: WorkspaceToUndeploy | undefined;
  loading?: boolean;
}

export default function UndeployWorkspaceModal({
  isOpen,
  onOpenChange,
  onConfirmAction,
  workspaceToUndeploy,
  loading = false,
}: UndeployWorkspaceModalProps) {
  const { t } = useTranslation('catalog', {
    keyPrefix: 'undeployModal',
  });

  if (!workspaceToUndeploy) return null;

  const handleConfirm = () => {
    if (loading) return;
    onConfirmAction(workspaceToUndeploy.workloadId);
  };

  const handleClose = () => {
    onOpenChange(false);
  };

  return (
    <ConfirmationModal
      confirmationButtonColor="danger"
      description={t('description', {
        name: workspaceToUndeploy.displayName,
      })}
      title={t('title')}
      isOpen={isOpen}
      loading={loading}
      onConfirm={handleConfirm}
      onClose={handleClose}
    />
  );
}
