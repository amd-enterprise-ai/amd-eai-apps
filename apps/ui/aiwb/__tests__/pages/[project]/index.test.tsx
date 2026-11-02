// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT
import { describe, expect, it } from 'vitest';

import { getLatestValue, isOverAllocatedQuota } from '@/pages/[project]/index';

describe('getLatestValue', () => {
  it('returns the most recent non-null value', () => {
    expect(
      getLatestValue([
        { timestamp: '1', value: 1 },
        { timestamp: '2', value: 2 },
        { timestamp: '3', value: 3 },
      ]),
    ).toBe(3);
  });

  it('skips trailing null values', () => {
    expect(
      getLatestValue([
        { timestamp: '1', value: 1 },
        { timestamp: '2', value: 2 },
        { timestamp: '3', value: null },
      ]),
    ).toBe(2);
  });

  it('returns null when every value is null', () => {
    expect(
      getLatestValue([
        { timestamp: '1', value: null },
        { timestamp: '2', value: null },
      ]),
    ).toBeNull();
  });

  it('returns null for an empty series', () => {
    expect(getLatestValue([])).toBeNull();
  });
});

describe('isOverAllocatedQuota', () => {
  it('is false when the project has no dedicated quota', () => {
    expect(isOverAllocatedQuota(false, 0, 5)).toBe(false);
  });

  it('is false when latest usage is below the quota', () => {
    expect(isOverAllocatedQuota(true, 8, 5)).toBe(false);
  });

  it('is true when latest usage exceeds the quota', () => {
    expect(isOverAllocatedQuota(true, 4, 5)).toBe(true);
  });

  it('is false when latest usage exactly equals the quota', () => {
    expect(isOverAllocatedQuota(true, 5, 5)).toBe(false);
  });

  it('is false when there is no latest usage value', () => {
    expect(isOverAllocatedQuota(true, 4, null)).toBe(false);
  });
});
