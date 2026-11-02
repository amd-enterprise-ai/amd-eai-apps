// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { ReactNode } from 'react';

import { ActionFieldHintType } from '@amdenterpriseai/types';

export type DropdownItemHint = {
  type: ActionFieldHintType;
  message: string;
};

export type DropdownActionItem = {
  key: string;
  className?: string;
  onPress: () => void;
  startContent?: ReactNode;
  color?: string;
  label: string;
  hint?: DropdownItemHint[];
  isDisabled?: boolean;
  description?: string | ReactNode;
  showDivider?: boolean;
  actions?: DropdownActionItem[];
  isSection?: boolean;
};
