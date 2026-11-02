// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { act, render, screen } from '@testing-library/react';

import { QuotaUtilizationCard } from '@/components/features/projects';

const mockData = (
  numerator: Array<{ value?: number | null; timestamp?: string }>,
  denominator: Array<{ value?: number | null; timestamp?: string }>,
) => ({
  numerator: numerator.map((item, idx) => ({
    value: item.value,
    timestamp: item.timestamp ?? `2024-01-01T00:00:0${idx}Z`,
  })),
  denominator: denominator.map((item, idx) => ({
    value: item.value,
    timestamp: item.timestamp ?? `2024-01-01T00:00:0${idx}Z`,
  })),
});

describe('QuotaUtilizationCard', () => {
  it('renders loading state', () => {
    act(() => {
      render(<QuotaUtilizationCard data={mockData([], [])} isLoading={true} />);
    });
    expect(
      screen.getByText('dashboard.overview.quotaUtilizationAvg.title'),
    ).toBeInTheDocument();
  });

  it('renders noData when numerator or denominator is empty', () => {
    act(() => {
      render(<QuotaUtilizationCard data={mockData([], [])} />);
    });
    expect(screen.getByText('statistics.noData')).toBeInTheDocument();
  });

  it('excludes values if either numerator or denominator are null for a datapoint', () => {
    act(() => {
      render(
        <QuotaUtilizationCard
          data={mockData(
            [{ value: 1 }, { value: null }, { value: 5 }],
            [{ value: null }, { value: 2 }, { value: 4 }],
          )}
        />,
      );
    });

    // (5 / 4) = 0.5 -> 125.00%
    expect(screen.getByText('125.00%')).toBeInTheDocument();
  });

  it('excludes values if either numerator or denominator are undefined for a datapoint', () => {
    act(() => {
      render(
        <QuotaUtilizationCard
          data={mockData(
            [{ value: 1 }, { value: undefined }, { value: 5 }],
            [{ value: undefined }, { value: 2 }, { value: 4 }],
          )}
        />,
      );
    });

    // Only the third datapoint has both values: (5 / 4) -> 125.00%
    expect(screen.getByText('125.00%')).toBeInTheDocument();
  });

  it('calculates and renders correct percentage', () => {
    act(() => {
      render(
        <QuotaUtilizationCard
          data={mockData(
            [{ value: 2 }, { value: 3 }],
            [{ value: 4 }, { value: 6 }],
          )}
        />,
      );
    });
    // (2+3)/(4+6) = 0.5 -> 50.00%
    expect(screen.getByText('50.00%')).toBeInTheDocument();
  });

  it('renders noData when sumDenominator is 0', () => {
    act(() => {
      render(
        <QuotaUtilizationCard
          data={mockData(
            [{ value: 1 }, { value: 2 }],
            [{ value: 0 }, { value: 0 }],
          )}
        />,
      );
    });
    expect(screen.getByText('statistics.noData')).toBeInTheDocument();
  });

  it('does not throw when numerator is shorter than denominator', () => {
    act(() => {
      render(
        <QuotaUtilizationCard
          data={mockData([{ value: 2 }], [{ value: 4 }, { value: 6 }])}
        />,
      );
    });
    // Only the first index has a numerator: (2 / 4) -> 50.00%
    expect(screen.getByText('50.00%')).toBeInTheDocument();
  });
});
