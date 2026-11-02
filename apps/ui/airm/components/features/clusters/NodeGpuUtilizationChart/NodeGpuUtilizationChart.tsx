// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import {
  Card,
  CardBody,
  CardHeader,
  DynamicValueLegend,
  LineChart,
  Tab,
  Tabs,
} from '@amdenterpriseai/components';
import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'next-i18next';

import type { AvailableChartColorsKeys } from '@amdenterpriseai/types';
import type { TimeRange } from '@amdenterpriseai/types';

import {
  fetchNodeGpuClockSpeed,
  fetchNodeGpuUtilization,
  fetchNodeGpuVramUtilization,
} from '@/services/app';
import { mergeGpuDeviceTimeseriesToChartData } from '@/utils/node-gpu-utilization';
import { GpuUtilizationTabId } from '@/types/enums/clusters';
import {
  CLOCK_SPEED_TICK_COUNT,
  GPU_UTILIZATION_TAB_IDS,
} from '@/constants/clusters/nodeDetail';
import {
  getClusterNodeTimeRangeQueryKeyPrefix,
  filterGpuDevicesBySelection,
  getGpuChartCategories,
  getGpuChartColors,
} from '@/utils/cluster-nodes';
import { computeLinearChartMax } from '@amdenterpriseai/utils/app';

interface Props {
  clusterId: string;
  nodeId: string;
  timeRange: TimeRange;
  selectedGpuDevices: Set<string>;
  gpuColorMap: Map<string, number>;
  isDevicesLoading: boolean;
}

const translationKeySet = ['clusters', 'common'] as const;

export const NodeGpuUtilizationChart: React.FC<Props> = ({
  clusterId,
  nodeId,
  timeRange,
  selectedGpuDevices,
  gpuColorMap,
  isDevicesLoading,
}) => {
  const { t } = useTranslation(translationKeySet);
  const [gpuUtilizationTab, setGpuUtilizationTab] =
    useState<GpuUtilizationTabId>(GpuUtilizationTabId.Memory);
  const [hoveredChartPoint, setHoveredChartPoint] = useState<Record<
    string,
    unknown
  > | null>(null);
  const [activeLegendGpu, setActiveLegendGpu] = useState<string | undefined>(
    undefined,
  );

  const queryKeyBase = getClusterNodeTimeRangeQueryKeyPrefix(
    clusterId,
    nodeId,
    timeRange,
  );

  const gpuUtilizationQuery = useQuery({
    queryKey: [...queryKeyBase, 'gpu-utilization'],
    queryFn: () =>
      fetchNodeGpuUtilization(
        clusterId,
        nodeId,
        timeRange.start,
        timeRange.end,
      ),
    enabled: gpuUtilizationTab === GpuUtilizationTabId.GpuUsage,
  });

  const gpuVramUtilizationQuery = useQuery({
    queryKey: [...queryKeyBase, 'gpu-vram-utilization'],
    queryFn: () =>
      fetchNodeGpuVramUtilization(
        clusterId,
        nodeId,
        timeRange.start,
        timeRange.end,
      ),
    enabled: gpuUtilizationTab === GpuUtilizationTabId.Memory,
  });

  const gpuClockSpeedQuery = useQuery({
    queryKey: [...queryKeyBase, 'gpu-clock-speed'],
    queryFn: () =>
      fetchNodeGpuClockSpeed(clusterId, nodeId, timeRange.start, timeRange.end),
    enabled: gpuUtilizationTab === GpuUtilizationTabId.Clock,
  });

  const activeQuery =
    gpuUtilizationTab === GpuUtilizationTabId.Memory
      ? gpuVramUtilizationQuery
      : gpuUtilizationTab === GpuUtilizationTabId.Clock
        ? gpuClockSpeedQuery
        : gpuUtilizationQuery;

  const gpuDevicesToShow = useMemo(
    () =>
      filterGpuDevicesBySelection(
        activeQuery.data?.gpuDevices ?? [],
        selectedGpuDevices,
      ),
    [activeQuery.data?.gpuDevices, selectedGpuDevices],
  );

  const chartData = useMemo(
    () => mergeGpuDeviceTimeseriesToChartData(gpuDevicesToShow),
    [gpuDevicesToShow],
  );

  const chartCategories = useMemo(
    () => getGpuChartCategories(gpuDevicesToShow),
    [gpuDevicesToShow],
  );

  const chartColors = useMemo(
    () => getGpuChartColors(gpuDevicesToShow, gpuColorMap),
    [gpuDevicesToShow, gpuColorMap],
  );

  const chartUnit =
    gpuUtilizationTab === GpuUtilizationTabId.Clock ? 'MHz' : '%';

  const chartValueFormatter = useMemo((): ((v: number) => string) => {
    if (gpuUtilizationTab === GpuUtilizationTabId.Clock)
      return (v: number) => `${Number(v).toFixed(0)} MHz`;
    return (v: number) => `${Number(v).toFixed(0)}%`;
  }, [gpuUtilizationTab]);

  const chartMaxValue = useMemo(() => {
    if (gpuUtilizationTab === GpuUtilizationTabId.Clock) {
      const allValues = gpuDevicesToShow.flatMap(
        (d) => d.metric?.values.map((v) => v.value) ?? [],
      );
      if (allValues.length === 0) return undefined;
      return computeLinearChartMax(
        Math.max(...allValues),
        CLOCK_SPEED_TICK_COUNT,
      );
    }
    return 100;
  }, [gpuUtilizationTab, gpuDevicesToShow]);

  const chartTickCount = useMemo(() => {
    if (gpuUtilizationTab === GpuUtilizationTabId.Clock)
      return CLOCK_SPEED_TICK_COUNT;
    return undefined;
  }, [gpuUtilizationTab]);

  // Non-percentage labels (e.g. "2500 MHz") are wider and wrap to two lines at
  // the default yAxisWidth, clipping the topmost tick. Extra top margin prevents
  // that clipping.
  const chartMarginTop =
    gpuUtilizationTab === GpuUtilizationTabId.Clock ? 20 : undefined;

  const isLoading = activeQuery.isLoading || isDevicesLoading;
  const showNoData = !activeQuery.isLoading && gpuDevicesToShow.length === 0;

  const tabItems = useMemo(
    () =>
      GPU_UTILIZATION_TAB_IDS.map((tabId) => ({
        id: tabId,
        title:
          tabId === GpuUtilizationTabId.Memory
            ? t(
                'clusters:nodes.detail.deviceMetrics.gpuUtilization.tabMemoryUtilization',
              )
            : tabId === GpuUtilizationTabId.Clock
              ? t(
                  'clusters:nodes.detail.deviceMetrics.gpuUtilization.tabClockSpeed',
                )
              : t(
                  'clusters:nodes.detail.deviceMetrics.gpuUtilization.tabGpuUsage',
                ),
      })),
    [t],
  );

  return (
    <Card className="min-h-[120px]">
      <CardHeader className="pb-2">
        <div className="flex flex-wrap items-center justify-between gap-2 w-full">
          <span className="text-sm font-semibold text-foreground">
            {t('clusters:nodes.detail.deviceMetrics.gpuUtilization.title')}
          </span>
          <Tabs
            variant="primary"
            aria-label={t(
              'clusters:nodes.detail.deviceMetrics.gpuUtilization.title',
            )}
            selectedKey={gpuUtilizationTab}
            onSelectionChange={(key) =>
              setGpuUtilizationTab(key as GpuUtilizationTabId)
            }
            classNames={{
              base: 'w-fit',
              panel: 'hidden',
              tabList: 'dark:bg-default-hover',
            }}
            items={tabItems}
          >
            {(item) => <Tab key={item.id} title={item.title} />}
          </Tabs>
        </div>
      </CardHeader>
      <CardBody className="pt-0 mt-4">
        {showNoData ? (
          <p className="text-muted text-sm">
            {t('clusters:nodes.detail.deviceMetrics.noData')}
          </p>
        ) : (
          <>
            <LineChart
              data={chartData}
              index="date"
              categories={chartCategories}
              colors={chartColors as AvailableChartColorsKeys[]}
              valueFormatter={chartValueFormatter}
              minValue={0}
              yAxisTickCount={chartTickCount}
              marginTop={chartMarginTop}
              maxValue={chartMaxValue}
              showLegend={false}
              showYAxis={true}
              connectNulls={true}
              className="h-72"
              yAxisWidth={64}
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
                unit={chartUnit}
                isLoading={isLoading}
                valueFormatter={chartValueFormatter}
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
