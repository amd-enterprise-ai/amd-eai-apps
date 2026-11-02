// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { resolveFormFieldVariant } from '../../src/internal/formFieldVariant';

describe('resolveFormFieldVariant', () => {
  it('defaults to secondary when variant is omitted', () => {
    expect(resolveFormFieldVariant()).toBe('secondary');
    expect(resolveFormFieldVariant(undefined)).toBe('secondary');
  });

  it('passes through primary and secondary', () => {
    expect(resolveFormFieldVariant('primary')).toBe('primary');
    expect(resolveFormFieldVariant('secondary')).toBe('secondary');
  });
});
