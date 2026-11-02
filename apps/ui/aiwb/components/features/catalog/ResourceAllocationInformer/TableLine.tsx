// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { Chip, Skeleton, Tooltip, cn } from '@amdenterpriseai/components';
import { IconAlertTriangle } from '@tabler/icons-react';
import { JSX, memo, useMemo } from 'react';
import {
  ALLOCATION_STATUS_TEXT_CLASS,
  ResourceType,
  type AllocationAlertColor,
} from './constants';
import { useTranslation } from 'next-i18next';

/**
 * Props for TableLine component.
 */
export interface TableLineProps {
  multiplier?: number;
  value: number;
  quota?: number;
  req: number;
  type: ResourceType;
  isLoading?: boolean;
}

/**
 * TableLine component displays a resource allocation line.
 */
export const TableLine = memo(
  ({
    multiplier = 1,
    value,
    quota,
    req = 0,
    type,
    isLoading = false,
  }: TableLineProps): JSX.Element => {
    const { t } = useTranslation('catalog', {
      keyPrefix: 'deployModal.settings.resourceAllocation',
    });
    const total: number = useMemo(
      () => value * multiplier,
      [value, multiplier],
    );

    const { lineLabel, valueFormatted } = useMemo(() => {
      switch (type) {
        case ResourceType.GPU:
          return {
            lineLabel: t('gpuLabel'),
            valueFormatted: total,
          };
        case ResourceType.CPU:
          return {
            lineLabel: t('cpuLabel'),
            valueFormatted: t('cpuFormattedValue', { count: total }),
          };
        case ResourceType.RAM:
          return {
            lineLabel: t('ramLabel'),
            valueFormatted: t('ramFormattedValue', { count: total }),
          };
      }
    }, [type, t, total]);

    const { hasWarning, warningMessage, statusColor } = useMemo((): {
      hasWarning: boolean;
      warningMessage: string;
      statusColor: AllocationAlertColor | undefined;
    } => {
      const hasWarning = total < req || (quota ? total > quota : false);
      if (!hasWarning) {
        return {
          hasWarning: false,
          warningMessage: '',
          statusColor: undefined,
        };
      }

      if (total < req && quota && total > quota) {
        return {
          hasWarning: true,
          warningMessage: t('belowRequiredExceedsQuotaTooltip'),
          statusColor: 'danger',
        };
      }
      if (total < req) {
        return {
          hasWarning: true,
          warningMessage: t('belowRequiredTooltip'),
          statusColor: 'danger',
        };
      }
      return {
        hasWarning: true,
        warningMessage: t('exceedsQuotaTooltip'),
        statusColor: 'warning',
      };
    }, [total, quota, req, t]);

    const statusTextClass = statusColor
      ? ALLOCATION_STATUS_TEXT_CLASS[statusColor]
      : undefined;

    if (isLoading) {
      return (
        <div className="flex gap-4 h-6 items-center">
          <Skeleton className="w-full h-6 rounded-lg" />
          <Skeleton className="w-20 h-6 rounded-lg" />
          <Skeleton className="w-20 h-6 rounded-lg" />
        </div>
      );
    }

    return (
      <div className="flex gap-2 h-6 items-center">
        <span className="w-full flex gap-2 items-center">
          {hasWarning && (
            <Tooltip
              size="sm"
              content={warningMessage}
              className="max-w-[300px]"
            >
              <IconAlertTriangle
                size={16}
                className={cn('cursor-help', statusTextClass)}
              />
            </Tooltip>
          )}
          {lineLabel}
          {quota && quota > 0 && (
            <Chip size="sm" variant="flat">
              {t('quotaFormatted', {
                value: quota,
              })}
            </Chip>
          )}
        </span>
        {multiplier > 1 && (
          <span className="text-nowrap text-foreground/50">
            {t('perGPU', {
              value: value,
            })}
          </span>
        )}
        <span className={cn('text-nowrap', statusTextClass)}>
          {valueFormatted}
        </span>
      </div>
    );
  },
);

TableLine.displayName = 'TableLine';

export default TableLine;
