// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { components } from '@/types/api';

export enum InferenceMetricsColors {
  TIME_TO_FIRST_TOKEN = 'blue',
  INTER_TOKEN_LATENCY = 'emerald',
  END_TO_END_LATENCY = 'amber',
  WAITING_REQUESTS = 'blue',
  RUNNING_REQUESTS = 'green',
}

export type TimeSeriesResponse = components['schemas']['MetricsTimeseries'];
