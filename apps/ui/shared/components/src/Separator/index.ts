// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// HeroUI v3 renamed `Divider` to `Separator`. Keep the `Divider` alias so
// existing consumers do not need to change their import name.
import { Separator as SeparatorBase } from '@heroui/react';

export const Separator = SeparatorBase;
export const Divider = SeparatorBase;
export type { SeparatorProps } from '@heroui/react';
