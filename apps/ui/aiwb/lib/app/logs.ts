// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { LogLevel } from '@/types/workloads';

const LOG_LEVEL_COLORS: Record<LogLevel, string> = {
  trace: '#999999',
  debug: '#666666',
  info: '#11a8cd',
  warning: '#e5e510',
  error: '#f14c4c',
  critical: '#ff0000',
  unknown: '#666666',
};

export const getLogLevelColor = (level: LogLevel): string => {
  return LOG_LEVEL_COLORS[level] || LOG_LEVEL_COLORS.unknown;
};
