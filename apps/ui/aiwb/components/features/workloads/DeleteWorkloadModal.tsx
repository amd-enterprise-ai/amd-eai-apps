// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useTranslation } from 'next-i18next';

import type { Workload } from '@/types/workloads';
import type { EnrichedWorkloadMetrics } from '@/types/projects';

import { ConfirmationModal } from '@amdenterpriseai/components';

interface DeleteWorkloadModalProps {
  isOpen: boolean;
  onOpenChange: (isOpen: boolean) => void;
  onConfirmAction: (id: string) => void;
  workload:
    | Pick<Workload, 'id' | 'displayName'>
    | Pick<EnrichedWorkloadMetrics, 'id' | 'displayName'>
    | undefined;
}

export default function DeleteWorkloadModal({
  isOpen,
  onOpenChange,
  onConfirmAction,
  workload,
}: DeleteWorkloadModalProps) {
  const { t } = useTranslation('workloads');

  if (!workload) return null;

  const handleConfirm = () => {
    onConfirmAction(workload.id);
    onOpenChange(false);
  };

  return (
    <ConfirmationModal
      confirmationButtonColor="danger"
      description={t('list.actions.delete.confirmation.description', {
        name: workload.displayName || '',
      })}
      title={t('list.actions.delete.confirmation.title')}
      isOpen={isOpen}
      loading={false}
      onConfirm={handleConfirm}
      onClose={() => onOpenChange(false)}
    />
  );
}
