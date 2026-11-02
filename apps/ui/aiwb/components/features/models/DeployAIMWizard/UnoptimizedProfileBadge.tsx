// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { Alert } from '@amdenterpriseai/components';
import { IconAlertTriangle } from '@tabler/icons-react';
import { useTranslation } from 'next-i18next';

export const UnoptimizedProfileBadge = () => {
  const { t } = useTranslation('models');
  return (
    <span className="flex items-center gap-1.5 text-xs shrink-0 whitespace-nowrap">
      <IconAlertTriangle className="text-warning" size={14} aria-hidden />
      <span className="text-foreground">
        {t('deployAIM.fields.metric.unoptimizedLabel')}
      </span>
    </span>
  );
};

export const UnoptimizedAlert = ({
  hasOptimizedAlternative,
}: {
  hasOptimizedAlternative: boolean;
}) => {
  const { t } = useTranslation('models');
  return (
    <Alert
      status="warning"
      title={t(
        hasOptimizedAlternative
          ? 'deployAIM.fields.metric.unoptimizedSelectedLabel'
          : 'deployAIM.fields.metric.unoptimizedLabel',
      )}
      description={t(
        hasOptimizedAlternative
          ? 'deployAIM.fields.metric.unoptimizedSelectedDescription'
          : 'deployAIM.fields.metric.notOptimized',
      )}
      classNames={{
        title: 'text-foreground',
        description: 'text-foreground',
      }}
    />
  );
};
