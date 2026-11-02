// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { transformTimeSeriesDataToChartData } from '@/lib/app/workloads';

describe('transformTimeSeriesDataToChartData', () => {
  it('should transform time series data into chart data', () => {
    const mockTimeStamp1 = new Date();
    const mockTimeStamp2 = new Date(mockTimeStamp1.getTime() + 15 * 60 * 1000);
    const input = [
      {
        metadata: { category: { id: '1', name: 'Category 1' } },
        values: [
          { timestamp: mockTimeStamp1.toISOString(), value: 10 },
          { timestamp: mockTimeStamp2.toISOString(), value: 20 },
        ],
      },
      {
        metadata: { category: { id: '2', name: 'Category 2' } },
        values: [
          { timestamp: mockTimeStamp1.toISOString(), value: 30 },
          { timestamp: mockTimeStamp2.toISOString(), value: 40 },
        ],
      },
    ];
    const timestamps = [
      mockTimeStamp1.toISOString(),
      mockTimeStamp2.toISOString(),
    ];

    const result = transformTimeSeriesDataToChartData(
      input,
      timestamps,
      'category',
    );
    expect(result.data).toEqual([
      {
        date: mockTimeStamp1.toISOString(),
        'Category 1': 10,
        'Category 2': 30,
      },
      {
        date: mockTimeStamp2.toISOString(),
        'Category 1': 20,
        'Category 2': 40,
      },
    ]);
    expect(result.categories).toEqual(['Category 1', 'Category 2']);
  });

  it('maps null, undefined, and omitted values to null and missing datapoints to 0', () => {
    const ts1 = '2024-01-01T00:00:00Z';
    const ts2 = '2024-01-01T00:05:00Z';
    const input = [
      {
        metadata: { category: { id: '1', name: 'Category 1' } },
        values: [
          { timestamp: ts1, value: null },
          { timestamp: ts2, value: undefined },
        ],
      },
      {
        metadata: { category: { id: '2', name: 'Category 2' } },
        values: [{ timestamp: ts1 }],
      },
    ];
    const result = transformTimeSeriesDataToChartData(
      input,
      [ts1, ts2],
      'category',
    );
    expect(result.data).toEqual([
      { date: ts1, 'Category 1': null, 'Category 2': null },
      { date: ts2, 'Category 1': null, 'Category 2': 0 },
    ]);
  });
});
