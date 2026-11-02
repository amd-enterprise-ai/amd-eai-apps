// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// HeroUI v3 renamed `NumberInput` to `NumberField`. Keep the `NumberInput`
// alias so existing consumers do not need to change their import name.
export { NumberField, NumberInput } from './NumberField';
export type { NumberFieldProps, NumberInputProps } from './NumberField';
