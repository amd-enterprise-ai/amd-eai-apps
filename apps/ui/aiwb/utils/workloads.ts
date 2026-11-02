// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { IconCircleCaretRight, IconQuestionMark } from '@tabler/icons-react';

import {
  AvailableChartColorsKeys,
  Intent,
  StatusBadgeVariant,
} from '@amdenterpriseai/types';
import type { ResourceStatus } from '@/types/workloads';

export const WORKLOAD_STATUS_COLOR_MAP: Record<
  ResourceStatus,
  AvailableChartColorsKeys
> = {
  Failed: 'red',
  Pending: 'gray',
  Running: 'blue',
  Complete: 'green',
  Unknown: 'darkgray',
  Deleted: 'emerald',
  Deleting: 'fuchsia',
  Degraded: 'amber',
  Starting: 'violet',
};

export const getWorkloadStatusVariants = (
  t: (key: string) => string,
): Record<ResourceStatus, StatusBadgeVariant> => ({
  Complete: {
    label: t('status.Complete'),
    intent: Intent.SUCCESS,
  },
  Degraded: {
    label: t('status.Degraded'),
    intent: Intent.WARNING,
  },
  Running: {
    label: t('status.Running'),
    color: 'primary',
    icon: IconCircleCaretRight,
  },
  Deleting: {
    label: t('status.Deleting'),
    intent: Intent.PENDING,
    color: 'warning',
  },
  Pending: {
    label: t('status.Pending'),
    intent: Intent.PENDING,
  },
  Starting: {
    label: t('status.Starting'),
    intent: Intent.PENDING,
  },
  Failed: {
    label: t('status.Failed'),
    intent: Intent.DANGER,
  },
  Deleted: {
    label: t('status.Deleted'),
    intent: Intent.DANGER,
  },
  Unknown: {
    label: t('status.Unknown'),
    icon: IconQuestionMark,
    color: 'danger',
  },
});

export default getWorkloadStatusVariants;
