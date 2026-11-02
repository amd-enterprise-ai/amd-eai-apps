// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { act, render, screen } from '@testing-library/react';

import { StatsWithLineChart } from '@amdenterpriseai/components';

describe('StatsWithLineChart', () => {
  it('renders component', () => {
    const { container } = render(
      <StatsWithLineChart
        title={'Card title'}
        tooltip={'test tooltip content'}
        data={[]}
      />,
    );
    expect(container).toBeTruthy();
    expect(screen.queryByText('Card title')).toBeInTheDocument();
  });

  it('renders data of last data point by default', () => {
    act(() => {
      render(
        <StatsWithLineChart
          title={'Card title'}
          tooltip={'test tooltip content'}
          data={[
            { timestamp: '2024-01-01T00:00:00Z', value: 10 },
            { timestamp: '2024-01-02T00:00:00Z', value: 20 },
            { timestamp: '2024-01-03T00:00:00Z', value: 30 },
          ]}
        />,
      );
    });
    expect(screen.getByText('30.00')).toBeInTheDocument();
  });

  it('renders data of last data point by default with upper limit', () => {
    act(() => {
      render(
        <StatsWithLineChart
          title={'Card title'}
          tooltip={'test tooltip content'}
          data={[
            { timestamp: '2024-01-01T00:00:00Z', value: 10 },
            { timestamp: '2024-01-02T00:00:00Z', value: 20 },
            { timestamp: '2024-01-03T00:00:00Z', value: 30 },
          ]}
          upperLimitData={[
            { timestamp: '2024-01-01T00:00:00Z', value: 11 },
            { timestamp: '2024-01-02T00:00:00Z', value: 22 },
            { timestamp: '2024-01-03T00:00:00Z', value: 33 },
          ]}
          upperLimitFormatter={(val) =>
            `/ ${Number(val).toFixed(2)} some test units`
          }
        />,
      );
    });
    expect(screen.getByText('30.00')).toBeInTheDocument();
    expect(screen.getByText('/ 33.00 some test units')).toBeInTheDocument();
  });

  it('renders timestamp correctly', () => {
    act(() => {
      render(
        <StatsWithLineChart
          title={'Card title'}
          tooltip={'test tooltip content'}
          data={[
            { timestamp: '2024-01-01T00:00:00Z', value: 10 },
            { timestamp: '2024-01-02T00:00:00Z', value: 20 },
            { timestamp: '2024-01-03T00:00:00Z', value: 30 },
          ]}
          upperLimitData={[
            { timestamp: '2024-01-01T00:00:00Z', value: 11 },
            { timestamp: '2024-01-02T00:00:00Z', value: 22 },
            { timestamp: '2024-01-03T00:00:00Z', value: 33 },
          ]}
          upperLimitFormatter={(val) =>
            `/ ${Number(val).toFixed(2)} some test units`
          }
        />,
      );
    });
    const lastDate = new Date('2024-01-03T00:00:00Z');
    const lastTimeStr = lastDate.toLocaleTimeString();
    const lastDateStr = lastDate.toLocaleDateString();
    expect(screen.getByText(new RegExp(lastTimeStr))).toBeInTheDocument();
    expect(screen.getByText(new RegExp(lastDateStr))).toBeInTheDocument();
  });

  it('renders last available data point correctly', () => {
    act(() => {
      render(
        <StatsWithLineChart
          title={'Card title'}
          tooltip={'test tooltip content'}
          data={[
            { timestamp: '2024-01-01T00:00:00Z', value: 10 },
            { timestamp: '2024-01-02T00:00:00Z', value: 20 },
            { timestamp: '2024-01-03T00:00:00Z', value: 30 },
            { timestamp: '2024-01-04T00:00:00Z', value: null },
          ]}
          upperLimitData={[
            { timestamp: '2024-01-01T00:00:00Z', value: 11 },
            { timestamp: '2024-01-02T00:00:00Z', value: 22 },
            { timestamp: '2024-01-03T00:00:00Z', value: 33 },
            { timestamp: '2024-01-04T00:00:00Z', value: null },
          ]}
          upperLimitFormatter={(val) =>
            `/ ${Number(val).toFixed(2)} some test units`
          }
        />,
      );
    });
    const lastValidDate = new Date('2024-01-03T00:00:00Z');
    const lastTimeStr = lastValidDate.toLocaleTimeString();
    const lastDateStr = lastValidDate.toLocaleDateString();
    expect(screen.getByText(new RegExp(lastTimeStr))).toBeInTheDocument();
    expect(screen.getByText(new RegExp(lastDateStr))).toBeInTheDocument();
  });

  it('renders last available data point correctly with undefined and omitted values', () => {
    act(() => {
      render(
        <StatsWithLineChart
          title={'Card title'}
          tooltip={'test tooltip content'}
          data={[
            { timestamp: '2024-01-01T00:00:00Z', value: 10 },
            { timestamp: '2024-01-02T00:00:00Z', value: 20 },
            { timestamp: '2024-01-03T00:00:00Z', value: 30 },
            { timestamp: '2024-01-04T00:00:00Z', value: undefined },
            { timestamp: '2024-01-05T00:00:00Z' },
          ]}
          upperLimitData={[
            { timestamp: '2024-01-01T00:00:00Z', value: 11 },
            { timestamp: '2024-01-02T00:00:00Z', value: 22 },
            { timestamp: '2024-01-03T00:00:00Z', value: 33 },
            { timestamp: '2024-01-04T00:00:00Z', value: undefined },
            { timestamp: '2024-01-05T00:00:00Z' },
          ]}
          upperLimitFormatter={(val) =>
            `/ ${Number(val).toFixed(2)} some test units`
          }
        />,
      );
    });
    const lastValidDate = new Date('2024-01-03T00:00:00Z');
    const lastTimeStr = lastValidDate.toLocaleTimeString();
    const lastDateStr = lastValidDate.toLocaleDateString();
    expect(screen.getByText(new RegExp(lastTimeStr))).toBeInTheDocument();
    expect(screen.getByText(new RegExp(lastDateStr))).toBeInTheDocument();
  });
});
