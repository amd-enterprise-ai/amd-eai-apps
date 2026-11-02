// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useTranslation } from 'next-i18next';

import { WORKLOAD_STATUS_COLOR_MAP } from '@/utils/workloads';

import type { components } from '@/types/api';

import { CategorySplitStatsCard } from '@amdenterpriseai/components';

interface Props {
  projectName: string;
  totalWorkloads: number;
  data: components['schemas']['WorkloadStatusCount'][];
  isLoading?: boolean;
}

export const ProjectWorkloadsStatsCard: React.FC<Props> = ({
  data,
  projectName,
  totalWorkloads,
  isLoading,
}) => {
  const { t } = useTranslation('projects');
  const { t: workloadsT } = useTranslation('workloads');

  return (
    <div className="flex grow">
      <CategorySplitStatsCard
        title={
          <div className="flex gap-2 items-center font-light text-nowrap">
            {t('dashboard.overview.workloadStates.title')}
            <span className="font-bold">{projectName}</span>
          </div>
        }
        total={
          <div className="flex gap-2 items-end font-light text-nowrap">
            <span className="text-2xl font-bold">{totalWorkloads}</span>
            <span className="mb-0.5">
              {t('dashboard.overview.workloadStates.total')}
            </span>
          </div>
        }
        data={
          data
            ? {
                title: t('dashboard.overview.workloadStates.subtitle'),
                total: totalWorkloads,
                values: data.map((status) => ({
                  label: workloadsT(`status.${status.status}`),
                  value: status.count,
                  color: WORKLOAD_STATUS_COLOR_MAP[status.status],
                })),
              }
            : null
        }
        isLoading={isLoading}
      />
    </div>
  );
};

export default ProjectWorkloadsStatsCard;
