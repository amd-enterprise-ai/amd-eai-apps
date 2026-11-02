// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { describe, expect, it } from 'vitest';

import { isValidK8sDnsSubdomain } from '@/lib/app/k8s-names';

describe('isValidK8sDnsSubdomain', () => {
  it('accepts lowercase DNS subdomain names', () => {
    expect(isValidK8sDnsSubdomain('my-hf-token')).toBe(true);
  });

  it('rejects uppercase and leading hyphens', () => {
    expect(isValidK8sDnsSubdomain('Invalid-Name')).toBe(false);
    expect(isValidK8sDnsSubdomain('-leading-hyphen')).toBe(false);
  });
});
