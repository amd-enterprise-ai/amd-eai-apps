// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { IconClock } from '@tabler/icons-react';
import { useTranslation } from 'next-i18next';

import { displayTimestamp } from '@amdenterpriseai/utils/app';
import { Intent } from '@amdenterpriseai/types';
import { Status } from '@amdenterpriseai/components';

import { AIMServiceCondition } from '@/types/aims';

enum ConditionStatus {
  READY = 'ready',
  FAILED = 'failed',
  PENDING = 'pending',
}

/**
 * Determines the status of a condition based on its type, status, and reason.
 * - Ready: type ends with "Ready" and status is "True"
 * - Failed: type ends with "Ready" and status is "False" and reason ends with "Failed"
 * - Pending: everything else
 */
const getConditionStatus = (
  condition: AIMServiceCondition,
): ConditionStatus => {
  const isReadyType = condition.type.endsWith('Ready');
  if (isReadyType && condition.status === 'True') {
    return ConditionStatus.READY;
  }
  if (
    isReadyType &&
    condition.status === 'False' &&
    condition.reason.endsWith('Failed')
  ) {
    return ConditionStatus.FAILED;
  }
  return ConditionStatus.PENDING;
};

/**
 * To sort the conditions by status.
 * Failed → Pending → Ready
 */
const statusOrder = {
  [ConditionStatus.FAILED]: 0,
  [ConditionStatus.PENDING]: 1,
  [ConditionStatus.READY]: 2,
};

const getConditionStatusProps = (
  status: ConditionStatus,
  t: (key: string) => string,
) => {
  const configs = {
    [ConditionStatus.READY]: {
      label: t('details.conditions.ready'),
      intent: Intent.SUCCESS,
    },
    [ConditionStatus.FAILED]: {
      label: t('details.conditions.failed'),
      intent: Intent.DANGER,
    },
    [ConditionStatus.PENDING]: {
      label: t('details.conditions.pending'),
      intent: Intent.WARNING,
      icon: IconClock,
    },
  };
  return configs[status] || configs[ConditionStatus.PENDING];
};

interface Props {
  conditions: AIMServiceCondition[];
}

/**
 * Renders a sorted list of AIM conditions (Failed → Pending → Ready),
 * filtering to only "*Ready" conditions and showing type, timestamp, message and status.
 */
const AIMConditionsList: React.FC<Props> = ({ conditions }) => {
  const { t } = useTranslation('workloads');

  const sortedConditions = conditions
    .filter((c) => c.type !== 'Ready' && c.type?.endsWith('Ready'))
    .map((c) => ({ ...c, computedStatus: getConditionStatus(c) }))
    .sort(
      (a, b) => statusOrder[a.computedStatus] - statusOrder[b.computedStatus],
    );

  if (sortedConditions.length === 0) return null;

  return (
    <div className="space-y-4">
      {sortedConditions.map((condition) => (
        <div
          key={condition.type}
          className="flex items-start justify-between border-b border-default pb-4 last:border-b-0 last:pb-0"
        >
          <div className="flex flex-col">
            <span className="font-medium text-sm">
              {condition.type.replace(/Ready$/, '')}
            </span>
            {condition.lastTransitionTime && (
              <span className="text-xs text-muted">
                {displayTimestamp(new Date(condition.lastTransitionTime))}
              </span>
            )}
            {condition.message && (
              <p className="text-xs text-muted mt-1">{condition.message}</p>
            )}
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            <Status
              {...getConditionStatusProps(condition.computedStatus, t)}
              isShowBackground={false}
              isTextColored={true}
              size="sm"
            />
          </div>
        </div>
      ))}
    </div>
  );
};

export default AIMConditionsList;
