// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { Card, CardBody, CardHeader } from '@amdenterpriseai/components';
import { IconInfoCircle } from '@tabler/icons-react';
import { useTranslation } from 'next-i18next';

interface WorkloadBasicInfoCardProps {
  name: string;
  workloadId: string;
  createdBy: string;
}

export const WorkloadBasicInfoCard: React.FC<WorkloadBasicInfoCardProps> = ({
  name,
  workloadId,
  createdBy,
}) => {
  const { t } = useTranslation('workloads');

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center gap-2">
          <IconInfoCircle size={18} className="text-muted" />
          <span className="text-sm font-medium">
            {t('details.sections.basicInformation')}
          </span>
        </div>
      </CardHeader>
      <CardBody className="pt-0 space-y-3 text-sm">
        <div className="space-y-0.5">
          <div className="text-muted">{t('details.fields.name')}</div>
          <div>{name}</div>
        </div>
        <div className="space-y-0.5">
          <div className="text-muted">{t('details.fields.workloadId')}</div>
          <div>{workloadId}</div>
        </div>
        <div className="space-y-0.5">
          <div className="text-muted">{t('details.fields.createdBy')}</div>
          <div>{createdBy}</div>
        </div>
      </CardBody>
    </Card>
  );
};
