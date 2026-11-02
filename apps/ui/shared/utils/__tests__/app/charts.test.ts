// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  generateSkeletonChartData,
  getFirstTimestampsOfDayIndices,
  isOver1Day,
  rollupTimeSeriesData,
  transformTimeSeriesDataToChartData,
} from '@amdenterpriseai/utils/app';
import { describe, it, expect } from 'vitest';

describe('rollupTimeSeriesData', () => {
  it('should return the original data if the length is 4 or less', () => {
    const mockTimeStamp = new Date();
    const input = {
      data: [
        {
          metadata: { someKey: { id: '1', name: 'Category 1' } },
          values: [{ timestamp: mockTimeStamp.toISOString(), value: 10 }],
        },
        {
          metadata: { someKey: { id: '2', name: 'Category 2' } },
          values: [{ timestamp: mockTimeStamp.toISOString(), value: 20 }],
        },
      ],
      range: {
        start: mockTimeStamp.toISOString(),
        end: mockTimeStamp.toISOString(),
        intervalSeconds: 300,
        timestamps: [mockTimeStamp.toISOString()],
      },
    };
    const result = rollupTimeSeriesData(input, 'Other', 'someKey');
    expect(result).toEqual(input.data);
  });

  it('should roll up data into "other" if the length is greater than 4', () => {
    const mockTimeStamp = new Date();

    const input = {
      data: [
        {
          metadata: { category: { id: '1', name: 'Category 1' } },
          values: [{ timestamp: mockTimeStamp.toISOString(), value: 10 }],
        },
        {
          metadata: { category: { id: '2', name: 'Category 2' } },
          values: [{ timestamp: mockTimeStamp.toISOString(), value: 20 }],
        },
        {
          metadata: { category: { id: '3', name: 'Category 3' } },
          values: [{ timestamp: mockTimeStamp.toISOString(), value: 30 }],
        },
        {
          metadata: { category: { id: '4', name: 'Category 4' } },
          values: [{ timestamp: mockTimeStamp.toISOString(), value: 40 }],
        },
        {
          metadata: { category: { id: '5', name: 'Category 5' } },
          values: [{ timestamp: mockTimeStamp.toISOString(), value: 50 }],
        },
      ],
      range: {
        start: mockTimeStamp.toISOString(),
        end: mockTimeStamp.toISOString(),
        intervalSeconds: 300,
        timestamps: [mockTimeStamp.toISOString()],
      },
    };
    const result = rollupTimeSeriesData(input, 'Other', 'category');
    expect(result.length).toBe(4);
    expect(
      result.find(
        (item) =>
          typeof item.metadata.category === 'object' &&
          item.metadata.category !== null &&
          'id' in item.metadata.category &&
          (item.metadata.category as { id: string }).id === 'other',
      ),
    ).toBeDefined();
  });
});

describe('generateSkeletonChartData', () => {
  it('should generate skeleton chart data with correct timestamps and values', () => {
    const loadingKey = 'loading';
    const result = generateSkeletonChartData(loadingKey);

    expect(result).toHaveLength(15);

    const now = new Date();
    const roundedToNext5Minutes = new Date(
      Math.ceil(now.getTime() / (5 * 60 * 1000)) * (5 * 60 * 1000),
    );

    const values = [40, 40, 35, 20, 15, 40, 70, 70, 15, 10, 0, 0, 20, 20, 10];
    const interval = 5 * 60 * 1000; // 5 minutes in milliseconds

    values.forEach((value, index) => {
      const expectedDate = new Date(
        roundedToNext5Minutes.getTime() -
          (values.length - 1 - index) * interval,
      ).toISOString();

      expect(result[index].date).toBe(expectedDate);
      expect(result[index][loadingKey]).toBe(value);
    });
  });

  it('should use the provided loading key for the values', () => {
    const loadingKey = 'customKey';
    const result = generateSkeletonChartData(loadingKey);

    result.forEach((point) => {
      expect(point).toHaveProperty(loadingKey);
    });
  });
});
describe('getFirstTimestampsOfDayIndices', () => {
  it('should return indices of the first timestamps of each day in local time', () => {
    const dates = [
      new Date('2023-03-01T10:00:00'),
      new Date('2023-03-01T15:00:00'),
      new Date('2023-03-02T09:00:00'),
      new Date('2023-03-03T08:00:00'),
    ];
    const result = getFirstTimestampsOfDayIndices(dates);
    expect(result).toEqual([0, 2, 3]);
  });

  it('should return indices of the first timestamps of each day in UTC', () => {
    const dates = [
      new Date('2023-03-01T23:00:00Z'),
      new Date('2023-03-02T01:00:00Z'),
      new Date('2023-03-02T15:00:00Z'),
      new Date('2023-03-03T00:00:00Z'),
    ];
    const result = getFirstTimestampsOfDayIndices(dates, true);
    expect(result).toEqual([0, 1, 3]);
  });

  it('should return an empty array if no dates are provided', () => {
    const dates: Date[] = [];
    const result = getFirstTimestampsOfDayIndices(dates);
    expect(result).toEqual([]);
  });

  it('should handle a single date correctly', () => {
    const dates = [new Date('2023-03-01T10:00:00')];
    const result = getFirstTimestampsOfDayIndices(dates);
    expect(result).toEqual([0]);
  });
});

describe('transformTimeSeriesDataToChartData', () => {
  const ts1 = '2024-01-01T00:00:00Z';
  const ts2 = '2024-01-01T00:05:00Z';

  it('maps a null value to null and a missing datapoint to 0', () => {
    const ts3 = '2024-01-01T00:10:00Z';
    const tsd = [
      {
        metadata: { category: { id: '1', name: 'Category 1' } },
        values: [
          { timestamp: ts1, value: 10 },
          { timestamp: ts2, value: null },
        ],
      },
    ];
    const result = transformTimeSeriesDataToChartData(
      tsd,
      [ts1, ts2, ts3],
      'category',
    );
    expect(result.data).toEqual([
      { date: ts1, 'Category 1': 10 },
      { date: ts2, 'Category 1': null },
      { date: ts3, 'Category 1': 0 },
    ]);
  });

  it('maps an undefined or omitted value to null (not 0)', () => {
    const tsd = [
      {
        metadata: { category: { id: '1', name: 'Category 1' } },
        values: [{ timestamp: ts1, value: undefined }, { timestamp: ts2 }],
      },
    ];
    const result = transformTimeSeriesDataToChartData(
      tsd,
      [ts1, ts2],
      'category',
    );
    expect(result.data).toEqual([
      { date: ts1, 'Category 1': null },
      { date: ts2, 'Category 1': null },
    ]);
  });
});

describe('isOver1Day', () => {
  it('should return true if the data spans more than 1 day', () => {
    const data = [
      { timestamp: '2023-03-01T10:00:00Z' },
      { timestamp: '2023-03-02T12:00:00Z' },
    ];
    const result = isOver1Day(data, 'timestamp');
    expect(result).toBe(true);
  });

  it('should return false if the data spans less than 1 day', () => {
    const data = [
      { timestamp: '2023-03-01T10:00:00Z' },
      { timestamp: '2023-03-01T15:00:00Z' },
    ];
    const result = isOver1Day(data, 'timestamp');
    expect(result).toBe(false);
  });

  it('should return false if the data has less than 2 entries', () => {
    const data = [{ timestamp: '2023-03-01T10:00:00Z' }];
    const result = isOver1Day(data, 'timestamp');
    expect(result).toBe(false);
  });

  it('should handle invalid date strings gracefully', () => {
    const data = [
      { timestamp: 'invalid-date' },
      { timestamp: '2023-03-02T12:00:00Z' },
    ];
    const result = isOver1Day(data, 'timestamp');
    expect(result).toBe(false);
  });
});
