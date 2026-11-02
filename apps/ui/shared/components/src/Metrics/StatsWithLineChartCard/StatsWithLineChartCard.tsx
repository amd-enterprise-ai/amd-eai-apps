// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

'use client';

import {
  Card,
  CardBody,
  CardHeader,
  Skeleton,
  Tooltip,
} from '@amdenterpriseai/components';
import { IconAlertTriangle, IconInfoCircle } from '@tabler/icons-react';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { AvailableChartColorsKeys } from '@amdenterpriseai/types';

import { TimeSeriesDataPoint } from '@amdenterpriseai/types';

import { LineChart, TooltipProps } from '../LineChart';

export interface Props {
  title: string;
  tooltip: string;
  /** When set, shows a warning icon next to the info tooltip with this message on hover. */
  alertTooltip?: string;
  data: TimeSeriesDataPoint[];
  dataFormatter?: (value: number | string) => string;
  upperLimitData?: TimeSeriesDataPoint[];
  upperLimitFormatter?: (value: number | string) => string;
  showValueAsPercentage?: boolean;
  isLoading?: boolean;
  width?: number;
  colors?: AvailableChartColorsKeys[];
  fillHeight?: boolean;
  /** When true, shows Y-axis labels to the left of the chart. */
  showYAxis?: boolean;
}

export const StatsWithLineChart: React.FC<Props> = ({
  title,
  tooltip,
  alertTooltip,
  colors,
  data,
  dataFormatter,
  upperLimitData,
  upperLimitFormatter,
  showValueAsPercentage = false,
  width = 350,
  isLoading = false,
  fillHeight = false,
  showYAxis = false,
}) => {
  const [currentValue, setCurrentValue] = useState<number>(
    data.length ? (data[data.length - 1].value ?? 0) : 0,
  );
  const [upperLimit, setUpperLimit] = useState<number>(
    upperLimitData?.length
      ? (upperLimitData[upperLimitData.length - 1].value ?? 0)
      : 0,
  );
  const [currentTimestamp, setCurrentTimestamp] = useState<string>(
    data.length ? data[data.length - 1].timestamp : '',
  );

  const timestampIndexMap = useMemo(() => {
    const map: Record<string | number, number> = {};
    data.forEach((item, idx) => {
      map[item.timestamp] = idx;
    });
    return map;
  }, [data]);

  const lastValidIndex = useMemo(() => {
    const lastDataIdx = [...data]
      .reverse()
      .findIndex((item) => item.value !== null && item.value !== undefined);
    return lastDataIdx >= 0 ? data.length - 1 - lastDataIdx : data.length - 1;
  }, [data]);

  useEffect(() => {
    setCurrentValue(
      lastValidIndex !== -1 ? (data[lastValidIndex].value ?? 0) : 0,
    );
    setUpperLimit(
      upperLimitData?.length && lastValidIndex !== -1
        ? (upperLimitData[lastValidIndex]?.value ?? 0)
        : 0,
    );
    setCurrentTimestamp(
      lastValidIndex !== -1 ? data[lastValidIndex].timestamp : '',
    );
  }, [upperLimitData, data, lastValidIndex]);

  const chartData = useMemo(() => {
    if (!upperLimitData || data.length !== upperLimitData.length) {
      return data;
    }

    if (!showValueAsPercentage) {
      return data.map((item, idx) => ({
        ...item,
        numerator: item.value ?? null,
        denominator: upperLimitData[idx].value ?? null,
      }));
    }

    return data.map((item, idx) => {
      const upperLimitValue = upperLimitData?.[idx].value;
      return {
        ...item,
        value: upperLimitValue
          ? ((item.value ?? 0) / upperLimitValue) * 100
          : 0,
      };
    });
  }, [data, upperLimitData, showValueAsPercentage]);

  const handleHoverChanges = useCallback(
    (props: TooltipProps) => {
      if (props.active) {
        const index = timestampIndexMap[props.label];
        setCurrentValue(data[index]?.value ?? 0);
        setUpperLimit(
          upperLimitData?.length ? (upperLimitData[index]?.value ?? 0) : 0,
        );
        setCurrentTimestamp(props.label);
      } else {
        setCurrentValue(
          lastValidIndex !== -1 ? (data[lastValidIndex].value ?? 0) : 0,
        );
        setUpperLimit(
          upperLimitData?.length && lastValidIndex !== -1
            ? (upperLimitData[lastValidIndex]?.value ?? 0)
            : 0,
        );
        setCurrentTimestamp(
          lastValidIndex !== -1 ? data[lastValidIndex].timestamp : '',
        );
      }
      return null;
    },
    [data, timestampIndexMap, upperLimitData, lastValidIndex],
  );

  const maxChartValue = useMemo(() => {
    if (!chartData.length) return 0;
    return Math.max(...chartData.map((item) => item.value ?? 0));
  }, [chartData]);

  return (
    <Card className={`max-w-full xl:max-w-[${width}px]  overflow-visible`}>
      <CardHeader>
        <div className="flex items-center flex-grow">
          <div>{title}</div>
          <div className="ml-auto flex items-center gap-2">
            {alertTooltip ? (
              <Tooltip content={alertTooltip} className="max-w-[300px]">
                <IconAlertTriangle
                  className="text-warning cursor-pointer"
                  size={16}
                />
              </Tooltip>
            ) : null}
            <Tooltip content={tooltip} className="max-w-[300px]">
              <IconInfoCircle className="text-muted cursor-pointer" size={16} />
            </Tooltip>
          </div>
        </div>
      </CardHeader>
      <CardBody className="overflow-visible pt-2">
        <div className={`flex items-stretch${fillHeight ? ' h-full' : ''}`}>
          <div className="w-32 flex flex-col justify-center text-nowrap">
            {isLoading ? (
              <Skeleton className="h-8 rounded-[3px] w-12" />
            ) : (
              <div className="text-2xl font-bold">
                {dataFormatter
                  ? dataFormatter(currentValue)
                  : currentValue.toFixed(2)}
              </div>
            )}
            {upperLimitData !== undefined ? (
              isLoading ? (
                <Skeleton className="rounded-[3px] h-3 w-16 mt-3" />
              ) : (
                <div className="text-sm font-light">
                  {upperLimitFormatter
                    ? upperLimitFormatter(upperLimit)
                    : upperLimit}
                </div>
              )
            ) : null}
            <div className="text-sm font-extralight mt-2">
              {isLoading ? (
                <Skeleton className="h-3 rounded-[3px] w-28" />
              ) : (
                <>
                  {new Date(currentTimestamp).toLocaleDateString()}{' '}
                  {new Date(currentTimestamp).toLocaleTimeString()}
                </>
              )}
            </div>
          </div>
          <div className="flex-1 flex items-center ml-4">
            <LineChart
              colors={colors}
              data={chartData}
              valueFormatter={
                upperLimitData && showValueAsPercentage
                  ? (value) => (upperLimitData ? `${value}%` : String(value))
                  : dataFormatter
                    ? (value) => String(dataFormatter(value))
                    : (value) => value.toString()
              }
              index="timestamp"
              showXAxis={false}
              showYAxis={showYAxis}
              showLegend={false}
              showTooltip={false}
              minValue={showValueAsPercentage ? 0 : undefined}
              maxValue={
                showValueAsPercentage && maxChartValue <= 100 ? 100 : undefined
              }
              tickGap={3}
              yAxisTickCount={3}
              categories={
                upperLimitData ? ['denominator', 'numerator'] : ['value']
              }
              startEndOnly
              className="h-20 w-full"
              customWidth={
                upperLimitData && !showValueAsPercentage
                  ? { 0: 0.75 }
                  : undefined
              }
              tooltipCallback={handleHoverChanges}
              xPadding={false}
              isLoading={isLoading}
            />
          </div>
        </div>
      </CardBody>
    </Card>
  );
};
