// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

export type FormFieldVariant = 'primary' | 'secondary';

export const resolveFormFieldVariant = (
  variant?: FormFieldVariant,
): FormFieldVariant => variant ?? 'secondary';
