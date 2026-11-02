// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { IconLoaderQuarter } from '@tabler/icons-react';

// Static variant configurations - computed once, reused everywhere
export const VARIANT_CONFIGS = {
  primary: { variant: 'primary' as const },
  secondary: { variant: 'tertiary' as const }, // default
  tertiary: { variant: 'ghost' as const },
  danger: { variant: 'danger' as const },
} as const;

// Static spinner element - created once, reused
export const SPINNER_ELEMENT = <IconLoaderQuarter className="animate-spin" />;
