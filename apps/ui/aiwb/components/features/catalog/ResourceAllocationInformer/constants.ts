// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { type Color } from '@amdenterpriseai/types';

/**
 * ResourceType enum for resource allocation types.
 */
export enum ResourceType {
  GPU = 'gpu',
  CPU = 'cpu',
  RAM = 'ram',
}

export type AllocationAlertColor = Extract<
  Exclude<Color, undefined>,
  'warning' | 'danger'
>;

export const ALLOCATION_STATUS_TEXT_CLASS: Record<
  AllocationAlertColor,
  string
> = {
  warning: 'text-warning',
  danger: 'text-danger',
};
