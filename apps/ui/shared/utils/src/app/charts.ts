// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { TimeRangePeriod } from '@amdenterpriseai/types';
import {
  PlotPoint,
  TimeSeriesData,
  TimeSeriesResponse,
} from '@amdenterpriseai/types';

export const rollupTimeSeriesData = (
  timeSeriesData: TimeSeriesResponse,
  otherCategoryString: string,
  metadataKey: string,
): TimeSeriesData[] => {
  let processedData: TimeSeriesData[] = [];
  if (timeSeriesData.data.length > 4) {
    const averageValues: { id: string; average: number }[] = timeSeriesData.data
      .map((entry) => {
        const total = entry.values.reduce(
          (sum, point) => sum + (point.value ?? 0),
          0,
        );
        const average = total / entry.values.length;
        const meta = entry.metadata[metadataKey];
        const id =
          typeof meta === 'object' && meta !== null && 'id' in meta
            ? (meta as { id: string }).id
            : String(meta);
        return { id, average };
      })
      .sort((a, b) => b.average - a.average);

    // extra top 3 average data sets
    const top3 = averageValues.slice(0, 3).map((item) => {
      return timeSeriesData.data.find((data) => {
        const meta = data.metadata[metadataKey];
        if (typeof meta === 'object' && meta !== null && 'id' in meta) {
          return (meta as { id: string }).id === item.id;
        }
        return String(meta) === item.id;
      });
    });

    // roll up data below top 3 into "other" data set
    const others = timeSeriesData.data
      .filter((data) => !top3.includes(data))
      .reduce(
        (acc, data) => {
          data.values.forEach((point, index) => {
            acc.values[index].value =
              (acc.values[index].value ?? 0) + (point.value ?? 0);
          });
          return acc;
        },
        {
          metadata: {
            [metadataKey]: { id: 'other', name: otherCategoryString },
          },
          values: timeSeriesData.data[0].values.map((point) => ({
            timestamp: point.timestamp,
            value: 0,
          })),
        },
      );

    processedData.push(
      ...top3.filter((item): item is TimeSeriesData => item !== undefined),
      others,
    );
  } else {
    processedData = timeSeriesData.data;
  }
  return processedData;
};

export const transformTimeSeriesDataToChartData = (
  tsd: TimeSeriesData[],
  timestamps: string[],
  metadataKey: string,
) => {
  return {
    data: timestamps.map((timestamp) => {
      return tsd.reduce(
        (acc: PlotPoint, group) => {
          const matchingData = group.values.find(
            (entry) => entry.timestamp === timestamp,
          );
          const meta = group.metadata[metadataKey];
          const categoryName =
            typeof meta === 'object' && meta !== null && 'name' in meta
              ? (meta as { name: string }).name
              : String(meta);
          acc[categoryName] = matchingData ? (matchingData.value ?? null) : 0;
          return acc;
        },
        { date: timestamp },
      );
    }),
    categories: tsd.map((data) => {
      const meta = data.metadata[metadataKey];
      return typeof meta === 'object' && meta !== null && 'name' in meta
        ? (meta as { name: string }).name
        : String(meta);
    }),
  };
};

export const generateSkeletonChartData = (loadingKey: string): PlotPoint[] => {
  const now = new Date();
  const roundedToNext5Minutes = new Date(
    Math.ceil(now.getTime() / (5 * 60 * 1000)) * (5 * 60 * 1000),
  );

  const values = [40, 40, 35, 20, 15, 40, 70, 70, 15, 10, 0, 0, 20, 20, 10];
  const interval = 5 * 60 * 1000; // 5 minutes in milliseconds

  return values.map((value, index) => {
    const date = new Date(
      roundedToNext5Minutes.getTime() - (values.length - 1 - index) * interval,
    );
    return { date: date.toISOString(), [loadingKey]: value };
  });
};

export const getFirstTimestampsOfDayIndices = (
  dates: Date[],
  utc: boolean = false,
): number[] => {
  return dates.reduce<number[]>((indices, date, index) => {
    const prevDate = dates[index - 1];
    const isNewDay = utc
      ? index === 0 ||
        date.getUTCDate() !== prevDate.getUTCDate() ||
        date.getUTCMonth() !== prevDate.getUTCMonth() ||
        date.getUTCFullYear() !== prevDate.getUTCFullYear()
      : index === 0 ||
        date.getDate() !== prevDate.getDate() ||
        date.getMonth() !== prevDate.getMonth() ||
        date.getFullYear() !== prevDate.getFullYear();

    if (isNewDay) {
      indices.push(index);
    }
    return indices;
  }, []);
};

export const isOver1Day = (data: Record<string, string>[], index: string) => {
  if (data.length < 2) return false;

  const firstDate = new Date(data[0][index]);
  const lastDate = new Date(data[data.length - 1][index]);
  return lastDate.getTime() - firstDate.getTime() > 24 * 60 * 60 * 1000;
};

export const getTickGap = (
  timePeriodRange?: TimeRangePeriod,
): number | undefined => {
  const shortRange = [
    TimeRangePeriod['15M'],
    TimeRangePeriod['30M'],
    TimeRangePeriod['1H'],
  ].includes(timePeriodRange as TimeRangePeriod);
  return shortRange ? 36 : undefined;
};
