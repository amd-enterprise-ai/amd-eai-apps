// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useMemo } from 'react';

import { useTranslation } from 'next-i18next';

import { TimeSeriesAllocationData } from '@amdenterpriseai/types';

import { StatisticsCard } from '@amdenterpriseai/components';

interface Props {
  data: TimeSeriesAllocationData;
  isLoading?: boolean;
}

export const QuotaUtilizationCard: React.FC<Props> = ({
  isLoading = false,
  data,
}) => {
  const { t } = useTranslation('projects');

  const quotaUtilizationAvg = useMemo(() => {
    const { numerator, denominator } = data;
    const { sumNumerator, sumDenominator } = denominator.reduce(
      (acc, denom, i) => {
        if (denom.value == null) return acc;
        const num = numerator[i]?.value;
        const bothValuesDefined = num != null;
        return {
          sumNumerator: acc.sumNumerator + (bothValuesDefined ? num : 0),
          sumDenominator:
            acc.sumDenominator + (bothValuesDefined ? denom.value : 0),
        };
      },
      { sumNumerator: 0, sumDenominator: 0 },
    );

    return sumDenominator === 0 ? undefined : sumNumerator / sumDenominator;
  }, [data]);

  return (
    <StatisticsCard
      title={t('dashboard.overview.quotaUtilizationAvg.title')}
      tooltip={t('dashboard.overview.quotaUtilizationAvg.description')}
      statistic={quotaUtilizationAvg}
      statisticFormatter={(val) => `${(val * 100).toFixed(2)}%`}
      isLoading={isLoading}
    />
  );
};

export default QuotaUtilizationCard;
