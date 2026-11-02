// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  BarChart,
  Card,
  CardBody,
  CardHeader,
  DynamicValueLegend,
} from '@amdenterpriseai/components';
import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'next-i18next';

import type { AvailableChartColorsKeys } from '@amdenterpriseai/types';
import type { TimeRange } from '@amdenterpriseai/types';

import { fetchNodePowerUsage } from '@/services/app';
import { mergeGpuDeviceTimeseriesToChartData } from '@/utils/node-gpu-utilization';
import {
  getClusterNodeTimeRangeQueryKeyPrefix,
  filterGpuDevicesBySelection,
  getGpuChartCategories,
  getGpuChartColors,
} from '@/utils/cluster-nodes';

interface Props {
  clusterId: string;
  nodeId: string;
  timeRange: TimeRange;
  selectedGpuDevices: Set<string>;
  gpuColorMap: Map<string, number>;
  isDevicesLoading: boolean;
}

const translationKeySet = ['clusters', 'common'] as const;

export const NodeGpuPowerUsageChart: React.FC<Props> = ({
  clusterId,
  nodeId,
  timeRange,
  selectedGpuDevices,
  gpuColorMap,
  isDevicesLoading,
}) => {
  const { t } = useTranslation(translationKeySet);
  const [hoveredChartPoint, setHoveredChartPoint] = useState<Record<
    string,
    unknown
  > | null>(null);
  const [activeLegendGpu, setActiveLegendGpu] = useState<string | undefined>(
    undefined,
  );

  const powerUsageQuery = useQuery({
    queryKey: [
      ...getClusterNodeTimeRangeQueryKeyPrefix(clusterId, nodeId, timeRange),
      'power-usage',
    ],
    queryFn: () =>
      fetchNodePowerUsage(clusterId, nodeId, timeRange.start, timeRange.end),
  });

  const devicesToShow = useMemo(
    () =>
      filterGpuDevicesBySelection(
        powerUsageQuery.data?.gpuDevices ?? [],
        selectedGpuDevices,
      ),
    [powerUsageQuery.data?.gpuDevices, selectedGpuDevices],
  );

  const chartData = useMemo(
    () => mergeGpuDeviceTimeseriesToChartData(devicesToShow),
    [devicesToShow],
  );

  const chartCategories = useMemo(
    () => getGpuChartCategories(devicesToShow),
    [devicesToShow],
  );

  const chartColors = useMemo(
    () => getGpuChartColors(devicesToShow, gpuColorMap),
    [devicesToShow, gpuColorMap],
  );

  const isLoading = powerUsageQuery.isLoading || isDevicesLoading;
  const showNoData = !powerUsageQuery.isLoading && devicesToShow.length === 0;

  return (
    <Card className="min-h-[120px]">
      <CardHeader className="pb-2">
        <span className="text-sm font-semibold text-foreground">
          {t('clusters:nodes.detail.deviceMetrics.gpuPowerConsumption.title')}
        </span>
      </CardHeader>
      <CardBody className="pt-0 mt-4">
        {showNoData ? (
          <p className="text-muted text-sm">
            {t('clusters:nodes.detail.deviceMetrics.noPowerData')}
          </p>
        ) : (
          <>
            <BarChart
              data={chartData}
              index="date"
              categories={chartCategories}
              colors={chartColors as AvailableChartColorsKeys[]}
              valueFormatter={(v: number) =>
                `${Number.isInteger(v) ? v : v.toFixed(2)}W`
              }
              allowDecimals={false}
              showLegend={false}
              showYAxis={true}
              className="h-72"
              activeLegendProp={activeLegendGpu}
              tooltipCallback={({ active, payload }) => {
                setHoveredChartPoint(
                  active && payload?.length
                    ? (payload[0].payload as Record<string, unknown>)
                    : null,
                );
              }}
              isLoading={isLoading}
            />
            {(isLoading || chartCategories.length > 0) && (
              <DynamicValueLegend
                categories={chartCategories}
                colors={chartColors as AvailableChartColorsKeys[]}
                data={chartData as Record<string, unknown>[]}
                unit="W"
                isLoading={isLoading}
                valueFormatter={(v) => `${Number(v).toFixed(2)}W`}
                displayPoint={hoveredChartPoint}
                activeCategory={activeLegendGpu}
                onCategoryClick={(category) =>
                  setActiveLegendGpu((prev) =>
                    prev === category ? undefined : category,
                  )
                }
              />
            )}
          </>
        )}
      </CardBody>
    </Card>
  );
};
