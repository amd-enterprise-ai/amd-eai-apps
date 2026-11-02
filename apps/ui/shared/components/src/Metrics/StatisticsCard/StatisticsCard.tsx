// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  Card,
  CardBody,
  CardHeader,
  Skeleton,
  Tooltip,
} from '@amdenterpriseai/components';
import { IconInfoCircle } from '@tabler/icons-react';

import { cn } from '@heroui/react';

import { useTranslation } from 'next-i18next';

export interface StatisticsCardProps {
  title: string;
  tooltip: string;
  statistic?: number;
  upperLimit?: number;
  isLoading?: boolean;
  statisticFormatter?: (val: number) => string;
  compact?: boolean;
  /** Override the CSS class on the value element, e.g. when the value is expected to be long text */
  valueClassName?: string;
}

export const StatisticsCard: React.FC<StatisticsCardProps> = ({
  title,
  tooltip,
  statistic,
  upperLimit,
  isLoading = false,
  statisticFormatter = (val) => val.toString(),
  compact = false,
  valueClassName,
}) => {
  const { t } = useTranslation('sharedComponents');
  const formattedStatistic =
    statistic !== undefined ? statisticFormatter(statistic) : undefined;

  return (
    <Card
      className={cn('max-w-full', {
        'h-full': compact,
        'min-h-[128px]': !compact,
      })}
    >
      <CardHeader className={cn({ 'py-2 px-4': compact })}>
        <div className="flex items-center flex-grow">
          <div className={cn({ 'text-sm': compact })}>{title}</div>
          <div className="ml-auto">
            <Tooltip content={tooltip} className="max-w-[300px]">
              <IconInfoCircle className="text-muted cursor-pointer" size={16} />
            </Tooltip>
          </div>
        </div>
      </CardHeader>
      <CardBody className={cn({ 'py-2 pt-0 px-4': compact })}>
        {isLoading && (
          <>
            <Skeleton
              className={cn('rounded-lg', {
                'h-3 w-20 mb-1': compact,
                'h-4 w-24 mb-2': !compact,
              })}
            />
            {upperLimit !== undefined && (
              <Skeleton className="h-3 rounded-lg w-16 mb-2" />
            )}
          </>
        )}
        {!isLoading && statistic !== undefined && (
          <>
            <div
              className={
                valueClassName ??
                cn('font-extrabold', {
                  'text-xl': compact,
                  'text-2xl': !compact,
                })
              }
              title={formattedStatistic}
            >
              {formattedStatistic}
            </div>
            {upperLimit !== undefined && (
              <div className="text-sm">
                {t('statistics.upperLimitPrefix')} {upperLimit}
              </div>
            )}
          </>
        )}
        {!isLoading && statistic === undefined && (
          <div
            className={cn('text-muted font-extrabold', {
              'text-lg': compact,
              'text-xl': !compact,
            })}
          >
            {t('statistics.noData')}
          </div>
        )}
      </CardBody>
    </Card>
  );
};
